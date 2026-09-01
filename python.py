import os
import random
import asyncio
import json
import re
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from collections import defaultdict

import requests
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import logging

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, Enum as SQLEnum, desc, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dombot.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Enums
class TaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"

class IntensityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

class MessageType(str, Enum):
    COMMAND = "command"
    CONVERSATION = "conversation"
    TASK = "task"
    ANALYSIS = "analysis"

class AvatarMood(str, Enum):
    COMMANDING = "commanding"
    PLEASED = "pleased"
    DISAPPOINTED = "disappointed"
    ANGRY = "angry"
    THOUGHTFUL = "thoughtful"
    SEDUCTIVE = "seductive"
    DOMINANT = "dominant"
    WORKOUT = "workout"

class RewardType(str, Enum):
    PRAISE = "praise"
    PRIVILEGE = "privilege"
    GIFT = "gift"
    REDUCED_INTENSITY = "reduced_intensity"
    SPECIAL_SELFIE = "special_selfie"
    CHOICE = "choice"
    REST_DAY = "rest_day"
    VIDEO_REWARD = "video_reward"
    MILESTONE = "milestone"
    RANDOM = "random"

# Database Models
class BotParameters(Base):
    __tablename__ = "bot_parameters"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"), unique=True)
    
    # Learning parameters
    learning_enabled = Column(Boolean, default=True)
    analysis_frequency = Column(Integer, default=5)
    adaptation_rate = Column(Float, default=0.3)
    
    # Behavior parameters
    possessiveness = Column(Float, default=0.6)
    degradation_level = Column(Float, default=0.4)
    psychological_focus = Column(Float, default=0.5)
    unpredictability = Column(Float, default=0.5)
    
    # Task parameters
    photo_demand_frequency = Column(Float, default=0.2)
    task_timeout_minutes = Column(Integer, default=30)
    escalation_threshold = Column(Integer, default=2)
    
    # Communication parameters
    verbosity = Column(String, default="medium")
    response_delay_enabled = Column(Boolean, default=True)
    min_response_delay_seconds = Column(Integer, default=2)
    max_response_delay_seconds = Column(Integer, default=10)
    
    # Scheduling
    min_interval_minutes = Column(Integer, default=60)
    max_interval_minutes = Column(Integer, default=180)
    active_hours_start = Column(Integer, default=8)
    active_hours_end = Column(Integer, default=23)
    
    # Content preferences
    preferred_task_types = Column(JSON, default=list)
    avoided_topics = Column(JSON, default=list)
    
    # Avatar parameters
    avatar_enabled = Column(Boolean, default=True)
    avatar_frequency = Column(Float, default=0.7)
    avatar_style = Column(String, default="photorealistic")
    avatar_ethnicity = Column(String, default="mixed")
    avatar_build = Column(String, default="muscular")
    avatar_hair = Column(String, default="dark")
    avatar_age_appearance = Column(String, default="28")
    
    # Reward parameters
    rewards_enabled = Column(Boolean, default=True)
    reward_frequency = Column(Float, default=0.1)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserState(Base):
    __tablename__ = "user_states"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, unique=True, index=True)
    intensity = Column(String, default=IntensityLevel.MEDIUM.value)
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    failed_tasks = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    last_message_time = Column(DateTime)
    last_response_time = Column(DateTime)
    awaiting_response = Column(Boolean, default=False)
    current_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    safe_word_active = Column(Boolean, default=False)
    safe_word_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    conversation_mode = Column(Boolean, default=True)
    
    # Learning data
    interaction_count = Column(Integer, default=0)
    last_analysis = Column(DateTime)
    relationship_notes = Column(Text, default="")
    learned_preferences = Column(JSON, default=dict)
    
    # Reward data
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    reward_points = Column(Integer, default=0)
    last_reward_date = Column(DateTime, nullable=True)
    privileges = Column(JSON, default=list)
    rest_day_until = Column(DateTime, nullable=True)
    
    # Relationships
    parameters = relationship("BotParameters", uselist=False, back_populates="user")
    tasks = relationship("Task", back_populates="user")
    messages = relationship("ConversationMessage")
    patterns = relationship("LearnedPattern")
    avatar_images = relationship("AvatarImage")
    rewards = relationship("Reward", order_by="Reward.created_at.desc()")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    description = Column(Text)
    task_type = Column(String, default="general")
    status = Column(String, default=TaskStatus.PENDING.value)
    requires_photo = Column(Boolean, default=False)
    intensity = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    deadline = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)
    photo_url = Column(String, nullable=True)
    escalation_count = Column(Integer, default=0)
    user_response_time = Column(Float, nullable=True)
    
    user = relationship("UserState", back_populates="tasks")

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    message = Column(Text)
    is_from_dom = Column(Boolean)
    message_type = Column(String, default=MessageType.CONVERSATION.value)
    timestamp = Column(DateTime, default=datetime.utcnow)
    emotional_tone = Column(String, nullable=True)
    has_avatar = Column(Boolean, default=False)

class LearnedPattern(Base):
    __tablename__ = "learned_patterns"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    pattern_type = Column(String)
    pattern_data = Column(JSON)
    confidence = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_observed = Column(DateTime, default=datetime.utcnow)

class AvatarImage(Base):
    __tablename__ = "avatar_images"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    mood = Column(String)
    image_data = Column(Text)
    prompt_used = Column(Text)
    generated_at = Column(DateTime, default=datetime.utcnow)
    use_count = Column(Integer, default=0)
    
    user = relationship("UserState", back_populates="avatar_images")

class Reward(Base):
    """Track rewards given"""
    __tablename__ = "rewards"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    reward_type = Column(String)
    description = Column(Text)
    triggered_by = Column(String)
    points_cost = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    redeemed = Column(Boolean, default=False)
    
    user = relationship("UserState", back_populates="rewards")

# Create tables
Base.metadata.create_all(bind=engine)

# Setup relationships
BotParameters.user = relationship("UserState", back_populates="parameters")

# App Configuration
app = FastAPI(title="Dom Bot - Trainable AI with Avatar & Rewards")
scheduler = BackgroundScheduler()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Venice API
VENICE_API_KEY = os.getenv("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"

# Constants
SAFE_WORD = os.getenv("SAFE_WORD", "RED")
CONVERSATION_HISTORY_LIMIT = 20

def get_db():
    db = SessionLocal()
    try:
        yield db
        return db
    finally:
        db.close()

def get_or_create_user(db: Session, chat_id: str):
    user = db.query(UserState).filter(UserState.chat_id == chat_id).first()
    if not user:
        user = UserState(chat_id=chat_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        
        params = BotParameters(user_id=user.id)
        db.add(params)
        db.commit()
    
    if not user.parameters:
        params = BotParameters(user_id=user.id)
        db.add(params)
        db.commit()
        db.refresh(user)
    
    return user

class RewardSystem:
    """Manages rewards and positive reinforcement"""
    
    REWARD_THRESHOLDS = {
        3: {"type": "praise", "message": "3 tasks completed. You're learning your place.", "points": 10},
        5: {"type": "reduced_intensity", "message": "5 tasks. I'm pleased. I'll be gentler... for now.", "points": 15},
        7: {"type": "privilege", "privilege": "late_response", "message": "7 tasks. You may have 10 extra minutes to respond.", "points": 20},
        10: {"type": "special_selfie", "mood": AvatarMood.SEDUCTIVE, "message": "10 tasks. You've earned a reward.", "points": 25},
        15: {"type": "choice", "message": "15 tasks. Choose your next task type: physical, mental, or service.", "points": 30},
        20: {"type": "rest_day", "message": "20 tasks. You may have 24 hours of light tasks only.", "points": 40},
        25: {"type": "video_reward", "message": "25 tasks. I'm generating something special for you.", "points": 50},
        50: {"type": "milestone", "message": "50 tasks. You are becoming an exemplary pet.", "points": 100},
    }
    
    STREAK_REWARDS = {
        3: {"type": "praise", "message": "3 in a row. Impressive.", "mood": AvatarMood.PLEASED},
        7: {"type": "special_selfie", "message": "7 consecutive. You deserve this.", "mood": AvatarMood.SEDUCTIVE},
        14: {"type": "privilege", "privilege": "task_choice", "message": "14 straight. Choose your next task.", "mood": AvatarMood.DOMINANT},
        30: {"type": "milestone", "message": "30 consecutive! You are devoted.", "mood": AvatarMood.SEDUCTIVE},
    }
    
    @staticmethod
    def check_milestones(user: UserState, db: Session):
        """Check if user hit a reward milestone"""
        if not user.parameters.rewards_enabled:
            return None
            
        completed = user.completed_tasks
        
        for threshold, reward_data in RewardSystem.REWARD_THRESHOLDS.items():
            if completed == threshold:
                existing = db.query(Reward).filter(
                    Reward.user_id == user.id,
                    Reward.triggered_by == f"milestone_{threshold}"
                ).first()
                
                if not existing:
                    return RewardSystem.grant_reward(user, db, reward_data, f"milestone_{threshold}")
        
        return None
    
    @staticmethod
    def check_streak_rewards(user: UserState, db: Session):
        """Check streak-based rewards"""
        if not user.parameters.rewards_enabled:
            return None
            
        streak = user.current_streak
        
        for threshold, reward_data in RewardSystem.STREAK_REWARDS.items():
            if streak == threshold:
                existing = db.query(Reward).filter(
                    Reward.user_id == user.id,
                    Reward.triggered_by == f"streak_{threshold}"
                ).first()
                
                if not existing:
                    reward = RewardSystem.grant_reward(user, db, {
                        "type": reward_data["type"],
                        "message": reward_data["message"],
                        "points": threshold * 2
                    }, f"streak_{threshold}")
                    reward.mood = reward_data.get("mood")
                    return reward
        
        return None
    
    @staticmethod
    def grant_reward(user: UserState, db: Session, reward_data: dict, triggered_by: str):
        """Grant a reward to user"""
        reward = Reward(
            user_id=user.id,
            reward_type=reward_data["type"],
            description=reward_data["message"],
            triggered_by=triggered_by,
            points_cost=0
        )
        db.add(reward)
        
        # Apply effects
        if reward_data["type"] == "reduced_intensity":
            user.intensity = deescalate_intensity(IntensityLevel(user.intensity)).value
        
        elif reward_data["type"] == "privilege":
            privs = user.privileges or []
            if "privilege" in reward_data:
                privs.append(reward_data["privilege"])
                user.privileges = privs
        
        elif reward_data["type"] == "rest_day":
            user.rest_day_until = datetime.utcnow() + timedelta(hours=24)
        
        elif reward_data["type"] == "praise":
            user.reward_points += reward_data.get("points", 10)
        
        user.last_reward_date = datetime.utcnow()
        db.commit()
        return reward
    
    @staticmethod
    def generate_reward_message(user: UserState, reward_type: str, context: str = "") -> str:
        """Generate contextual reward message"""
        prompts = {
            "praise": [
                "Good pet. You've pleased me.",
                "You obey well. I approve.",
                "Exactly as commanded. You're learning.",
                "Satisfactory. Continue.",
                "You serve me well. Remember this feeling."
            ],
            "seductive": [
                "You've earned my attention. Look at me.",
                "Come closer, pet. You've been good.",
                "I might let you see more... if you continue.",
                "Your obedience excites me.",
                "Perhaps I'll show you what you serve..."
            ],
            "proud": [
                "You've exceeded my expectations. Rare.",
                "I had doubts. You've erased them.",
                "You could serve as an example to others.",
                "My property is becoming valuable.",
                "I'm almost proud of my pet."
            ]
        }
        
        return random.choice(prompts.get(reward_type, prompts["praise"]))
    
    @staticmethod
    async def send_random_reward(user: UserState, db: Session):
        """Send spontaneous reward for good behavior"""
        if not user.parameters.rewards_enabled:
            return
            
        if not user.current_streak or user.current_streak < 2:
            return
        
        if random.random() > user.parameters.reward_frequency:
            return
        
        msg = RewardSystem.generate_reward_message(user, "praise")
        mood = random.choice([AvatarMood.PLEASED, AvatarMood.SEDUCTIVE])
        
        # Generate avatar
        try:
            from telegram import InputFile
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            
            if image_data:
                await bot.send_photo(
                    chat_id=user.chat_id,
                    photo=InputFile(io.BytesIO(image_data), filename="dom_random.jpg"),
                    caption=f"🎁 {msg}\n\n(You didn't expect this, did you?)"
                )
        except Exception as e:
            logger.error(f"Failed to send random reward: {e}")
            await bot.send_message(
                chat_id=user.chat_id,
                text=f"🎁 {msg}\n\n(You didn't expect this, did you?)"
            )
        
        reward = Reward(
            user_id=user.id,
            reward_type="random",
            description="Spontaneous praise for consistent behavior",
            triggered_by="random"
        )
        db.add(reward)
        db.commit()

class AvatarGenerator:
    """Generates Dom avatar images"""
    
    MOOD_PROMPTS = {
        AvatarMood.COMMANDING: {
            "description": "standing tall, arms crossed, intense eye contact, powerful stance",
            "clothing": "tight black briefs or jockstrap, harness",
            "expression": "intense, commanding, expectant",
            "setting": "minimalist dark room, dramatic lighting"
        },
        AvatarMood.PLEASED: {
            "description": "slight confident smile, relaxed posture, approving look",
            "clothing": "unbuttoned shirt or briefs showing physique",
            "expression": "satisfied, proud, approving",
            "setting": "bedroom or private gym"
        },
        AvatarMood.DISAPPOINTED: {
            "description": "crossed arms, head tilted, looking down",
            "clothing": "formal wear or leather",
            "expression": "disappointed, stern, judgmental",
            "setting": "office or dungeon"
        },
        AvatarMood.ANGRY: {
            "description": "fists clenched, leaning forward, aggressive",
            "clothing": "sweat-soaked tank or bare chest",
            "expression": "angry, furious, dangerous",
            "setting": "gym, harsh lighting"
        },
        AvatarMood.THOUGHTFUL: {
            "description": "sitting, contemplative, calculating",
            "clothing": "casual, sweatpants low, bare torso",
            "expression": "thoughtful, scheming",
            "setting": "private study"
        },
        AvatarMood.SEDUCTIVE: {
            "description": "reclining, inviting but dominant",
            "clothing": "minimal - briefs or towel",
            "expression": "seductive, tempting, knowing smirk",
            "setting": "luxury bedroom"
        },
        AvatarMood.DOMINANT: {
            "description": "standing over, power pose, ownership",
            "clothing": "leather harness, chaps, boots",
            "expression": "possessive, dominant",
            "setting": "dungeon or throne"
        },
        AvatarMood.WORKOUT: {
            "description": "sweaty post-workout, muscles pumped, glistening",
            "clothing": "tight compression shorts",
            "expression": "intense, focused, powerful",
            "setting": "gym or locker room"
        }
    }
    
    @staticmethod
    def build_prompt(user: UserState, mood: AvatarMood) -> str:
        params = user.parameters
        mood_data = AvatarGenerator.MOOD_PROMPTS.get(mood, AvatarGenerator.MOOD_PROMPTS[AvatarMood.COMMANDING])
        
        physical = f"{params.avatar_age_appearance}-year-old {params.avatar_ethnicity} man, {params.avatar_build} physique, {params.avatar_hair} hair"
        
        prompt = f"""{params.avatar_style} photograph of a dominant {physical}, {mood_data['description']}, 
{mood_data['clothing']}, {mood_data['expression']}, {mood_data['setting']},
highly detailed, professional lighting, masculine, powerful, 4k quality"""
        
        return prompt
    
    @staticmethod
    def generate_avatar(user: UserState, mood: AvatarMood, db: Session) -> Optional[bytes]:
        if not user.parameters.avatar_enabled:
            return None
        
        try:
            recent = db.query(AvatarImage).filter(
                AvatarImage.user_id == user.id,
                AvatarImage.mood == mood.value
            ).order_by(desc(AvatarImage.generated_at)).first()
            
            if recent and (datetime.utcnow() - recent.generated_at) < timedelta(hours=1) and recent.use_count < 3:
                recent.use_count += 1
                db.commit()
                return base64.b64decode(recent.image_data)
            
            prompt = AvatarGenerator.build_prompt(user, mood)
            
            response = requests.post(
                VENICE_IMAGE_URL,
                headers={
                    "Authorization": f"Bearer {VENICE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "chroma",
                    "prompt": prompt,
                    "width": 512,
                    "height": 768,
                    "seed": random.randint(1, 1000000)
                },
                timeout=60
            )
            
            if response.status_code == 200:
                image_data = response.json().get("images", [None])[0]
                if image_data:
                    avatar = AvatarImage(
                        user_id=user.id,
                        mood=mood.value,
                        image_data=image_data,
                        prompt_used=prompt,
                        use_count=1
                    )
                    db.add(avatar)
                    db.commit()
                    return base64.b64decode(image_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Avatar generation error: {e}")
            return None
    
    @staticmethod
    def determine_mood(user: UserState, context: str = "command") -> AvatarMood:
        if context == "task_assigned":
            return AvatarMood.COMMANDING
        elif context == "task_completed":
            if user.consecutive_failures == 0 and user.current_streak >= 7:
                return AvatarMood.SEDUCTIVE
            elif user.consecutive_failures == 0:
                return AvatarMood.PLEASED
            else:
                return AvatarMood.THOUGHTFUL
        elif context == "task_failed":
            if user.consecutive_failures > 2:
                return AvatarMood.ANGRY
            else:
                return AvatarMood.DISAPPOINTED
        elif context == "seduction":
            return AvatarMood.SEDUCTIVE
        elif context == "workout":
            return AvatarMood.WORKOUT
        elif user.intensity == IntensityLevel.EXTREME.value:
            return AvatarMood.DOMINANT
        else:
            return random.choice([AvatarMood.COMMANDING, AvatarMood.THOUGHTFUL])

class LearningEngine:
    """Analyzes patterns and updates bot behavior"""
    
    @staticmethod
    def analyze_user(db: Session, user: UserState):
        if not user.parameters.learning_enabled:
            return
        
        tasks = db.query(Task).filter(Task.user_id == user.id).all()
        if len(tasks) < 3:
            return
        
        type_stats = defaultdict(lambda: {"completed": 0, "failed": 0})
        for task in tasks:
            task_type = task.task_type or "general"
            if task.status == TaskStatus.COMPLETED.value:
                type_stats[task_type]["completed"] += 1
            elif task.status == TaskStatus.FAILED.value:
                type_stats[task_type]["failed"] += 1
        
        for task_type, stats in type_stats.items():
            total = stats["completed"] + stats["failed"]
            if total >= 2:
                success_rate = stats["completed"] / total
                LearningEngine._store_pattern(db, user.id, "task_success", {
                    "task_type": task_type,
                    "success_rate": success_rate,
                    "sample_size": total
                }, confidence=min(total / 10, 1.0))
        
        response_times = [t.user_response_time for t in tasks if t.user_response_time]
        if response_times:
            avg_response = sum(response_times) / len(response_times)
            LearningEngine._store_pattern(db, user.id, "response_time", {
                "average_seconds": avg_response,
                "pattern": "fast" if avg_response < 300 else "slow"
            })
        
        LearningEngine._generate_relationship_notes(db, user)
        
        preferences = {}
        for pattern in db.query(LearnedPattern).filter(LearnedPattern.user_id == user.id).all():
            if pattern.pattern_type == "task_success":
                task_type = pattern.pattern_data.get("task_type")
                success_rate = pattern.pattern_data.get("success_rate", 0)
                preferences[f"{task_type}_tasks"] = success_rate
        
        user.learned_preferences = preferences
        user.last_analysis = datetime.utcnow()
        db.commit()
    
    @staticmethod
    def _store_pattern(db: Session, user_id: int, pattern_type: str, data: dict, confidence: float = 0.5):
        existing = db.query(LearnedPattern).filter(
            LearnedPattern.user_id == user_id,
            LearnedPattern.pattern_type == pattern_type
        ).first()
        
        if existing:
            existing.pattern_data = data
            existing.confidence = confidence
            existing.last_observed = datetime.utcnow()
        else:
            pattern = LearnedPattern(
                user_id=user_id,
                pattern_type=pattern_type,
                pattern_data=data,
                confidence=confidence
            )
            db.add(pattern)
        db.commit()
    
    @staticmethod
    def _generate_relationship_notes(db: Session, user: UserState):
        recent_tasks = db.query(Task).filter(
            Task.user_id == user.id
        ).order_by(desc(Task.created_at)).limit(10).all()
        
        if len(recent_tasks) < 3:
            return
        
        task_summary = []
        for t in recent_tasks:
            status = "obeyed" if t.status == TaskStatus.COMPLETED.value else "disobeyed"
            task_summary.append(f"- {t.task_type}: {status}")
        
        prompt = f"""Analyze this BDSM dynamic:
        
Recent tasks:
{chr(10).join(task_summary)}

Overall: {user.completed_tasks}/{user.total_tasks} tasks obeyed
Streak: {user.current_streak}
Consecutive failures: {user.consecutive_failures}

Write 2-3 sentences summarizing what works, their psychology, effective tactics."""

        try:
            response = requests.post(
                VENICE_API_URL,
                headers={
                    "Authorization": f"Bearer {VENICE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 200
                },
                timeout=30
            )
            
            if response.status_code == 200:
                user.relationship_notes = response.json()["choices"][0]["message"]["content"]
                db.commit()
        except Exception as e:
            logger.error(f"Failed to generate notes: {e}")

def build_adaptive_system_prompt(user: UserState, db: Session) -> str:
    params = user.parameters
    
    possessive_phrases = {
        0.0: "You are a distant Dominant",
        0.3: "You are a casual Dominant",
        0.6: "You are a possessive Dominant who frequently claims ownership",
        0.9: "You are an obsessively possessive Dominant"
    }.get(round(params.possessiveness * 10) / 10, "You are a Dominant")
    
    degradation_adj = {
        0.0: "Use respectful language",
        0.3: "Mild teasing",
        0.6: "Regular degradation",
        0.9: "Extreme degradation"
    }.get(round(params.degradation_level * 10) / 10, "Moderate")
    
    psych_focus = "Focus on psychological domination" if params.psychological_focus > 0.5 else "Focus on physical commands"
    
    length_guide = {"short": "1-2 sentences", "medium": "2-4 sentences", "long": "4-8"}.get(params.verbosity, "2-4")
    
    notes = user.relationship_notes or "New relationship"
    
    return f"""{possessive_phrases}. {degradation_adj}. {psych_focus}.
Verbosity: {length_guide}. Intensity: {user.intensity}.
Relationship: {notes}. Never break character."""

def generate_ai_response(user: UserState, user_message: str, db: Session) -> str:
    try:
        system_prompt = build_adaptive_system_prompt(user, db)
        messages = [{"role": "system", "content": system_prompt}]
        
        history = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user.id
        ).order_by(desc(ConversationMessage.timestamp)).limit(10).all()
        
        for msg in reversed(history):
            role = "assistant" if msg.is_from_dom else "user"
            messages.append({"role": role, "content": msg.message})
        
        messages.append({"role": "user", "content": user_message})
        
        if user.parameters.response_delay_enabled:
            delay = random.randint(
                user.parameters.min_response_delay_seconds,
                user.parameters.max_response_delay_seconds
            )
            asyncio.create_task(asyncio.sleep(delay))
        
        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b",
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": 300
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return "Speak clearly."
            
    except Exception as e:
        logger.error(f"Error: {e}")
        return "Continue."

def determine_task_type(message: str, params: BotParameters) -> str:
    task_types = {
        "physical": ["pushup", "kneel", "hold", "position", "strip"],
        "mental": ["write", "recite", "remember", "focus"],
        "humiliation": ["beg", "admit", "confess"],
        "service": ["bring", "fetch", "prepare"],
        "denial": ["edge", "deny", "wait", "no touch"]
    }
    
    msg_lower = message.lower()
    scores = {t: sum(1 for kw in kws if kw in msg_lower) for t, kws in task_types.items()}
    if scores:
        return max(scores, key=scores.get)
    return random.choice(params.preferred_task_types or ["physical"])

def extract_task_from_message(message: str, params: BotParameters) -> Optional[dict]:
    task_indicators = [
        r"(?i)(send|show|give|take|do|complete).+?(me|photo)",
        r"(?i)(kneel|strip|hold|wait|edge|deny)",
        r"(?i)(your task is|you will|you must|obey)"
    ]
    
    for pattern in task_indicators:
        if re.search(pattern, message):
            return {
                "is_task": True,
                "task_type": determine_task_type(message, params),
                "requires_photo": random.random() < params.photo_demand_frequency
            }
    return None

def escalate_intensity(current: IntensityLevel) -> IntensityLevel:
    levels = list(IntensityLevel)
    idx = levels.index(current)
    return levels[idx + 1] if idx < len(levels) - 1 else current

def deescalate_intensity(current: IntensityLevel) -> IntensityLevel:
    levels = list(IntensityLevel)
    idx = levels.index(current)
    return levels[idx - 1] if idx > 0 else current

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_command: bool = False):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    params = user.parameters
    
    if user.safe_word_active and user.safe_word_until and datetime.utcnow() < user.safe_word_until:
        if update.message.text and SAFE_WORD in update.message.text.upper():
            pass
        else:
            await update.message.reply_text("🛑 Safe word active.")
            return
    
    user_text = update.message.text if update.message.text else "[image]"
    
    user_msg = ConversationMessage(user_id=user.id, message=user_text, is_from_dom=False)
    db.add(user_msg)
    user.interaction_count += 1
    
    if user.interaction_count % params.analysis_frequency == 0:
        LearningEngine.analyze_user(db, user)
    
    db.commit()
    
    ai_response = generate_ai_response(user, user_text, db)
    task_info = extract_task_from_message(ai_response, params)
    
    send_avatar = random.random() < params.avatar_frequency
    avatar_mood = AvatarMood.COMMANDING
    
    if task_info and task_info["is_task"]:
        send_avatar = True
        avatar_mood = AvatarGenerator.determine_mood(user, "task_assigned")
    elif random.random() < 0.3:
        avatar_mood = AvatarGenerator.determine_mood(user, "conversation")
    
    if task_info and task_info["is_task"]:
        deadline = datetime.utcnow() + timedelta(minutes=params.task_timeout_minutes)
        task = Task(
            user_id=user.id,
            description=ai_response,
            task_type=task_info["task_type"],
            requires_photo=task_info["requires_photo"],
            intensity=user.intensity,
            deadline=deadline
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        
        keyboard = [
            [InlineKeyboardButton("✓ Completed", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("✗ Failed", callback_data=f"fail_{task.id}")]
        ]
        if task_info["requires_photo"]:
            keyboard.insert(0, [InlineKeyboardButton("📸 Photo Proof", callback_data=f"photo_{task.id}")])
        
        dom_msg = ConversationMessage(user_id=user.id, message=ai_response, is_from_dom=True, has_avatar=send_avatar)
        db.add(dom_msg)
        db.commit()
        
        if send_avatar:
            image_data = AvatarGenerator.generate_avatar(user, avatar_mood, db)
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                    caption=ai_response,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(ai_response, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(ai_response, reply_markup=InlineKeyboardMarkup(keyboard))
        
        scheduler.add_job(
            lambda: asyncio.run(check_escalation_wrapper(str(update.effective_chat.id))),
            trigger=IntervalTrigger(minutes=params.task_timeout_minutes),
            id=f"escalation_check_{update.effective_chat.id}",
            replace_existing=True
        )
    else:
        dom_msg = ConversationMessage(user_id=user.id, message=ai_response, is_from_dom=True, has_avatar=send_avatar)
        db.add(dom_msg)
        db.commit()
        
        if send_avatar:
            image_data = AvatarGenerator.generate_avatar(user, avatar_mood, db)
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                    caption=ai_response
                )
            else:
                await update.message.reply_text(ai_response)
        else:
            await update.message.reply_text(ai_response)

async def check_escalation(db: Session, user: UserState):
    if not user.awaiting_response or not user.last_message_time:
        return
    
    params = user.parameters
    time_since = datetime.utcnow() - user.last_message_time
    
    if time_since > timedelta(minutes=params.task_timeout_minutes):
        user.intensity = escalate_intensity(IntensityLevel(user.intensity)).value
        user.consecutive_failures += 1
        user.current_streak = 0  # Reset streak on failure
        
        task = db.query(Task).filter(Task.id == user.current_task_id).first()
        if task:
            task.escalation_count += 1
        
        db.commit()
        
        msg = generate_ai_response(user, "My pet ignored me. I am escalating punishment.", db)
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.ANGRY, db)
        
        if image_data:
            await bot.send_photo(
                chat_id=user.chat_id,
                photo=InputFile(io.BytesIO(image_data), filename="dom_angry.jpg"),
                caption=f"⬆️ ESCALATION ⬆️\n\n{msg}"
            )
        else:
            await bot.send_message(chat_id=user.chat_id, text=f"⬆️ ESCALATION ⬆️\n\n{msg}")

async def check_escalation_wrapper(chat_id: str):
    db = next(get_db())
    user = get_or_create_user(db, chat_id)
    await check_escalation(db, user)

async def send_scheduled_dom_message():
    db = SessionLocal()
    user = get_or_create_user(db, USER_CHAT_ID)
    params = user.parameters
    
    if user.safe_word_active and user.safe_word_until and datetime.utcnow() < user.safe_word_until:
        return
    
    current_hour = datetime.utcnow().hour
    if not (params.active_hours_start <= current_hour <= params.active_hours_end):
        return
    
    # Check rest day
    if user.rest_day_until and datetime.utcnow() < user.rest_day_until:
        return
    
    prompts = [
        "I haven't spoken to my pet in a while. Remind them who owns them.",
        "Check in on my property. Demand something unexpected.",
        "My sub needs to be kept on their toes.",
        "Remind my pet what they are to me.",
        "Test my sub's devotion."
    ]
    
    message = generate_ai_response(user, random.choice(prompts), db)
    task_info = extract_task_from_message(message, params)
    
    if task_info and task_info["is_task"]:
        deadline = datetime.utcnow() + timedelta(minutes=params.task_timeout_minutes)
        task = Task(
            user_id=user.id,
            description=message,
            task_type=task_info["task_type"],
            requires_photo=task_info["requires_photo"],
            intensity=user.intensity,
            deadline=deadline
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        
        keyboard = [
            [InlineKeyboardButton("✓ Completed", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("✗ Failed", callback_data=f"fail_{task.id}")]
        ]
        if task_info["requires_photo"]:
            keyboard.insert(0, [InlineKeyboardButton("📸 Photo Proof", callback_data=f"photo_{task.id}")])
        
        dom_msg = ConversationMessage(user_id=user.id, message=message, is_from_dom=True, has_avatar=True)
        db.add(dom_msg)
        db.commit()
        
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.COMMANDING, db)
        
        if image_data:
            await bot.send_photo(
                chat_id=USER_CHAT_ID,
                photo=