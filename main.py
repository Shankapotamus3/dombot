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
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
import logging

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    Float,
    ForeignKey,
    Enum as SQLEnum,
    desc,
    JSON,
)
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


# Database Models - No relationships to avoid issues
class BotParameters(Base):
    __tablename__ = "bot_parameters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"), unique=True)
    learning_enabled = Column(Boolean, default=True)
    analysis_frequency = Column(Integer, default=5)
    adaptation_rate = Column(Float, default=0.3)
    possessiveness = Column(Float, default=0.6)
    degradation_level = Column(Float, default=0.4)
    psychological_focus = Column(Float, default=0.5)
    unpredictability = Column(Float, default=0.5)
    photo_demand_frequency = Column(Float, default=0.2)
    task_timeout_minutes = Column(Integer, default=30)
    escalation_threshold = Column(Integer, default=2)
    verbosity = Column(String, default="medium")
    response_delay_enabled = Column(Boolean, default=True)
    min_response_delay_seconds = Column(Integer, default=2)
    max_response_delay_seconds = Column(Integer, default=10)
    min_interval_minutes = Column(Integer, default=60)
    max_interval_minutes = Column(Integer, default=180)
    active_hours_start = Column(Integer, default=8)
    active_hours_end = Column(Integer, default=23)
    preferred_task_types = Column(JSON, default=list)
    avoided_topics = Column(JSON, default=list)
    avatar_enabled = Column(Boolean, default=True)
    avatar_frequency = Column(Float, default=0.7)
    avatar_style = Column(String, default="photorealistic")
    avatar_ethnicity = Column(String, default="mixed")
    avatar_build = Column(String, default="muscular")
    avatar_hair = Column(String, default="dark")
    avatar_age_appearance = Column(String, default="28")
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
    interaction_count = Column(Integer, default=0)
    last_analysis = Column(DateTime)
    relationship_notes = Column(Text, default="")
    learned_preferences = Column(JSON, default=dict)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    reward_points = Column(Integer, default=0)
    last_reward_date = Column(DateTime, nullable=True)
    privileges = Column(JSON, default=list)
    rest_day_until = Column(DateTime, nullable=True)


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


class Reward(Base):
    __tablename__ = "rewards"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    reward_type = Column(String)
    description = Column(Text)
    triggered_by = Column(String)
    points_cost = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    redeemed = Column(Boolean, default=False)


# Create tables
Base.metadata.create_all(bind=engine)

# Configuration
scheduler = BackgroundScheduler()

# API Keys
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
VENICE_API_KEY = os.getenv("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"
SAFE_WORD = os.getenv("SAFE_WORD", "RED")

bot = Bot(token=TELEGRAM_BOT_TOKEN)


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
    user.parameters = (
        db.query(BotParameters).filter(BotParameters.user_id == user.id).first()
    )
    return user


class RewardSystem:
    REWARD_THRESHOLDS = {
        3: {
            "type": "praise",
            "message": "3 tasks completed. You're learning your place.",
            "points": 10,
        },
        5: {
            "type": "reduced_intensity",
            "message": "5 tasks. I'm pleased. I'll be gentler... for now.",
            "points": 15,
        },
        7: {
            "type": "privilege",
            "privilege": "late_response",
            "message": "7 tasks. You may have 10 extra minutes to respond.",
            "points": 20,
        },
        10: {
            "type": "special_selfie",
            "mood": AvatarMood.SEDUCTIVE,
            "message": "10 tasks. You've earned a reward.",
            "points": 25,
        },
        15: {
            "type": "choice",
            "message": "15 tasks. Choose your next task type: physical, mental, or service.",
            "points": 30,
        },
        20: {
            "type": "rest_day",
            "message": "20 tasks. You may have 24 hours of light tasks only.",
            "points": 40,
        },
        25: {
            "type": "video_reward",
            "message": "25 tasks. I'm generating something special for you.",
            "points": 50,
        },
        50: {
            "type": "milestone",
            "message": "50 tasks. You are becoming an exemplary pet.",
            "points": 100,
        },
    }

    STREAK_REWARDS = {
        3: {
            "type": "praise",
            "message": "3 in a row. Impressive.",
            "mood": AvatarMood.PLEASED,
        },
        7: {
            "type": "special_selfie",
            "message": "7 consecutive. You deserve this.",
            "mood": AvatarMood.SEDUCTIVE,
        },
        14: {
            "type": "privilege",
            "privilege": "task_choice",
            "message": "14 straight. Choose your next task.",
            "mood": AvatarMood.DOMINANT,
        },
        30: {
            "type": "milestone",
            "message": "30 consecutive! You are devoted.",
            "mood": AvatarMood.SEDUCTIVE,
        },
    }

    @staticmethod
    def check_milestones(user: UserState, db: Session):
        if not user.parameters.rewards_enabled:
            return None
        completed = user.completed_tasks
        for threshold, reward_data in RewardSystem.REWARD_THRESHOLDS.items():
            if completed == threshold:
                existing = (
                    db.query(Reward)
                    .filter(
                        Reward.user_id == user.id,
                        Reward.triggered_by == f"milestone_{threshold}",
                    )
                    .first()
                )
                if not existing:
                    return RewardSystem.grant_reward(
                        user, db, reward_data, f"milestone_{threshold}"
                    )
        return None

    @staticmethod
    def check_streak_rewards(user: UserState, db: Session):
        if not user.parameters.rewards_enabled:
            return None
        streak = user.current_streak
        for threshold, reward_data in RewardSystem.STREAK_REWARDS.items():
            if streak == threshold:
                existing = (
                    db.query(Reward)
                    .filter(
                        Reward.user_id == user.id,
                        Reward.triggered_by == f"streak_{threshold}",
                    )
                    .first()
                )
                if not existing:
                    reward = RewardSystem.grant_reward(
                        user,
                        db,
                        {
                            "type": reward_data["type"],
                            "message": reward_data["message"],
                            "points": threshold * 2,
                        },
                        f"streak_{threshold}",
                    )
                    return reward
        return None

    @staticmethod
    def grant_reward(
        user: UserState, db: Session, reward_data: dict, triggered_by: str
    ):
        reward = Reward(
            user_id=user.id,
            reward_type=reward_data["type"],
            description=reward_data["message"],
            triggered_by=triggered_by,
            points_cost=0,
        )
        db.add(reward)
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
    def generate_reward_message(
        user: UserState, reward_type: str, context: str = ""
    ) -> str:
        prompts = {
            "praise": [
                "Good pet. You've pleased me.",
                "You obey well. I approve.",
                "Exactly as commanded.",
                "Satisfactory. Continue.",
                "You serve me well.",
            ],
            "seductive": [
                "You've earned my attention. Look at me.",
                "Come closer, pet.",
                "I might let you see more...",
                "Your obedience excites me.",
            ],
            "proud": [
                "You've exceeded my expectations.",
                "I had doubts. You've erased them.",
                "You could serve as an example.",
                "My property is becoming valuable.",
            ],
        }
        return random.choice(prompts.get(reward_type, prompts["praise"]))


class AvatarGenerator:
    MOOD_PROMPTS = {
        AvatarMood.COMMANDING: {
            "description": "standing tall, arms crossed, intense eye contact, powerful stance",
            "clothing": "tight black briefs or jockstrap, harness",
            "expression": "intense, commanding, expectant",
            "setting": "minimalist dark room, dramatic lighting",
        },
        AvatarMood.PLEASED: {
            "description": "slight confident smile, relaxed posture, approving look",
            "clothing": "unbuttoned shirt or briefs showing physique",
            "expression": "satisfied, proud, approving",
            "setting": "bedroom or private gym",
        },
        AvatarMood.DISAPPOINTED: {
            "description": "crossed arms, head tilted, looking down",
            "clothing": "formal wear or leather",
            "expression": "disappointed, stern, judgmental",
            "setting": "office or dungeon",
        },
        AvatarMood.ANGRY: {
            "description": "fists clenched, leaning forward, aggressive",
            "clothing": "sweat-soaked tank or bare chest",
            "expression": "angry, furious, dangerous",
            "setting": "gym, harsh lighting",
        },
        AvatarMood.THOUGHTFUL: {
            "description": "sitting, contemplative, calculating",
            "clothing": "casual, sweatpants low, bare torso",
            "expression": "thoughtful, scheming",
            "setting": "private study",
        },
        AvatarMood.SEDUCTIVE: {
            "description": "reclining, inviting but dominant",
            "clothing": "minimal - briefs or towel",
            "expression": "seductive, tempting, knowing smirk",
            "setting": "luxury bedroom",
        },
        AvatarMood.DOMINANT: {
            "description": "standing over, power pose, ownership",
            "clothing": "leather harness, chaps, boots",
            "expression": "possessive, dominant",
            "setting": "dungeon or throne",
        },
        AvatarMood.WORKOUT: {
            "description": "sweaty post-workout, muscles pumped, glistening",
            "clothing": "tight compression shorts",
            "expression": "intense, focused, powerful",
            "setting": "gym or locker room",
        },
    }

    @staticmethod
    def build_prompt(user: UserState, mood: AvatarMood) -> str:
        params = user.parameters
        mood_data = AvatarGenerator.MOOD_PROMPTS.get(
            mood, AvatarGenerator.MOOD_PROMPTS[AvatarMood.COMMANDING]
        )
        physical = f"{params.avatar_age_appearance}-year-old {params.avatar_ethnicity} man, {params.avatar_build} physique, {params.avatar_hair} hair"
        prompt = f"{params.avatar_style} photograph of a dominant {physical}, {mood_data['description']}, {mood_data['clothing']}, {mood_data['expression']}, {mood_data['setting']}, highly detailed, professional lighting, masculine, powerful, 4k quality"
        return prompt

    @staticmethod
    def generate_avatar(
        user: UserState, mood: AvatarMood, db: Session
    ) -> Optional[bytes]:
        if not user.parameters.avatar_enabled:
            return None
        try:
            recent = (
                db.query(AvatarImage)
                .filter(AvatarImage.user_id == user.id, AvatarImage.mood == mood.value)
                .order_by(desc(AvatarImage.generated_at))
                .first()
            )
            if (
                recent
                and (datetime.utcnow() - recent.generated_at) < timedelta(hours=1)
                and recent.use_count < 3
            ):
                recent.use_count += 1
                db.commit()
                return base64.b64decode(recent.image_data)
            prompt = AvatarGenerator.build_prompt(user, mood)
            response = requests.post(
                VENICE_IMAGE_URL,
                headers={
                    "Authorization": f"Bearer {VENICE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "chroma",
                    "prompt": prompt,
                    "width": 512,
                    "height": 768,
                    "seed": random.randint(1, 1000000),
                },
                timeout=60,
            )
            if response.status_code == 200:
                image_data = response.json().get("images", [None])[0]
                if image_data:
                    avatar = AvatarImage(
                        user_id=user.id,
                        mood=mood.value,
                        image_data=image_data,
                        prompt_used=prompt,
                        use_count=1,
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
                LearningEngine._store_pattern(
                    db,
                    user.id,
                    "task_success",
                    {
                        "task_type": task_type,
                        "success_rate": success_rate,
                        "sample_size": total,
                    },
                    confidence=min(total / 10, 1.0),
                )
        response_times = [t.user_response_time for t in tasks if t.user_response_time]
        if response_times:
            avg_response = sum(response_times) / len(response_times)
            LearningEngine._store_pattern(
                db,
                user.id,
                "response_time",
                {
                    "average_seconds": avg_response,
                    "pattern": "fast" if avg_response < 300 else "slow",
                },
            )
        LearningEngine._generate_relationship_notes(db, user)
        preferences = {}
        for pattern in (
            db.query(LearnedPattern).filter(LearnedPattern.user_id == user.id).all()
        ):
            if pattern.pattern_type == "task_success":
                task_type = pattern.pattern_data.get("task_type")
                success_rate = pattern.pattern_data.get("success_rate", 0)
                preferences[f"{task_type}_tasks"] = success_rate
        user.learned_preferences = preferences
        user.last_analysis = datetime.utcnow()
        db.commit()

    @staticmethod
    def _store_pattern(
        db: Session,
        user_id: int,
        pattern_type: str,
        data: dict,
        confidence: float = 0.5,
    ):
        existing = (
            db.query(LearnedPattern)
            .filter(
                LearnedPattern.user_id == user_id,
                LearnedPattern.pattern_type == pattern_type,
            )
            .first()
        )
        if existing:
            existing.pattern_data = data
            existing.confidence = confidence
            existing.last_observed = datetime.utcnow()
        else:
            pattern = LearnedPattern(
                user_id=user_id,
                pattern_type=pattern_type,
                pattern_data=data,
                confidence=confidence,
            )
            db.add(pattern)
        db.commit()

    @staticmethod
    def _generate_relationship_notes(db: Session, user: UserState):
        recent_tasks = (
            db.query(Task)
            .filter(Task.user_id == user.id)
            .order_by(desc(Task.created_at))
            .limit(10)
            .all()
        )
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
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 200,
                },
                timeout=30,
            )
            if response.status_code == 200:
                user.relationship_notes = response.json()["choices"][0]["message"][
                    "content"
                ]
                db.commit()
        except Exception as e:
            logger.error(f"Failed to generate notes: {e}")


def build_adaptive_system_prompt(user: UserState, db: Session) -> str:
    params = user.parameters
    possessive_phrases = {
        0.0: "You are a distant Dominant",
        0.3: "You are a casual Dominant",
        0.6: "You are a possessive Dominant who frequently claims ownership",
        0.9: "You are an obsessively possessive Dominant",
    }.get(round(params.possessiveness * 10) / 10, "You are a Dominant")
    degradation_adj = {
        0.0: "Use respectful language",
        0.3: "Mild teasing",
        0.6: "Regular degradation",
        0.9: "Extreme degradation",
    }.get(round(params.degradation_level * 10) / 10, "Moderate")
    psych_focus = (
        "Focus on psychological domination"
        if params.psychological_focus > 0.5
        else "Focus on physical commands"
    )
    length_guide = {
        "short": "1-2 sentences",
        "medium": "2-4 sentences",
        "long": "4-8",
    }.get(params.verbosity, "2-4")
    notes = user.relationship_notes or "New relationship"
    return f"{possessive_phrases}. {degradation_adj}. {psych_focus}. Verbosity: {length_guide}. Intensity: {user.intensity}. Relationship: {notes}. Never break character."


def generate_ai_response(user: UserState, user_message: str, db: Session) -> str:
    try:
        system_prompt = build_adaptive_system_prompt(user, db)
        messages = [{"role": "system", "content": system_prompt}]
        history = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.user_id == user.id)
            .order_by(desc(ConversationMessage.timestamp))
            .limit(10)
            .all()
        )
        for msg in reversed(history):
            role = "assistant" if msg.is_from_dom else "user"
            messages.append({"role": role, "content": msg.message})
        messages.append({"role": "user", "content": user_message})
        if user.parameters.response_delay_enabled:
            import time

            time.sleep(
                random.randint(
                    user.parameters.min_response_delay_seconds,
                    user.parameters.max_response_delay_seconds,
                )
            )
        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b",
                "messages": messages,
                "temperature": 0.85,
                "max_tokens": 300,
            },
            timeout=30,
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
        "denial": ["edge", "deny", "wait", "no touch"],
    }
    msg_lower = message.lower()
    scores = {
        t: sum(1 for kw in kws if kw in msg_lower) for t, kws in task_types.items()
    }
    if scores:
        return max(scores, key=scores.get)
    return random.choice(params.preferred_task_types or ["physical"])


def extract_task_from_message(message: str, params: BotParameters) -> Optional[dict]:
    task_indicators = [
        r"(?i)(send|show|give|take|do|complete).+?(me|photo)",
        r"(?i)(kneel|strip|hold|wait|edge|deny)",
        r"(?i)(your task is|you will|you must|obey)",
    ]
    for pattern in task_indicators:
        if re.search(pattern, message):
            return {
                "is_task": True,
                "task_type": determine_task_type(message, params),
                "requires_photo": random.random() < params.photo_demand_frequency,
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


async def process_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, is_command: bool = False
):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    params = user.parameters
    if (
        user.safe_word_active
        and user.safe_word_until
        and datetime.utcnow() < user.safe_word_until
    ):
        if update.message.text and SAFE_WORD in update.message.text.upper():
            pass
        else:
            await update.message.reply_text("🛑 Safe word active.")
            return
    user_text = update.message.text if update.message.text else "[image]"
    user_msg = ConversationMessage(
        user_id=user.id, message=user_text, is_from_dom=False
    )
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
            deadline=deadline,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        keyboard = [
            [InlineKeyboardButton("✓ Completed", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("✗ Failed", callback_data=f"fail_{task.id}")],
        ]
        if task_info["requires_photo"]:
            keyboard.insert(
                0,
                [
                    InlineKeyboardButton(
                        "📸 Photo Proof", callback_data=f"photo_{task.id}"
                    )
                ],
            )
        dom_msg = ConversationMessage(
            user_id=user.id,
            message=ai_response,
            is_from_dom=True,
            has_avatar=send_avatar,
        )
        db.add(dom_msg)
        db.commit()
        if send_avatar:
            image_data = AvatarGenerator.generate_avatar(user, avatar_mood, db)
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                    caption=ai_response,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                await update.message.reply_text(
                    ai_response, reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            await update.message.reply_text(
                ai_response, reply_markup=InlineKeyboardMarkup(keyboard)
            )
        scheduler.add_job(
            lambda: asyncio.run(
                check_escalation_wrapper(str(update.effective_chat.id))
            ),
            trigger=IntervalTrigger(minutes=params.task_timeout_minutes),
            id=f"escalation_check_{update.effective_chat.id}",
            replace_existing=True,
        )
    else:
        dom_msg = ConversationMessage(
            user_id=user.id,
            message=ai_response,
            is_from_dom=True,
            has_avatar=send_avatar,
        )
        db.add(dom_msg)
        db.commit()
        if send_avatar:
            image_data = AvatarGenerator.generate_avatar(user, avatar_mood, db)
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                    caption=ai_response,
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
        user.current_streak = 0
        task = db.query(Task).filter(Task.id == user.current_task_id).first()
        if task:
            task.escalation_count += 1
        db.commit()
        msg = generate_ai_response(
            user, "My pet ignored me. I am escalating punishment.", db
        )
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.ANGRY, db)
        if image_data:
            await bot.send_photo(
                chat_id=user.chat_id,
                photo=InputFile(io.BytesIO(image_data), filename="dom_angry.jpg"),
                caption=f"⬆️ ESCALATION ⬆️\n\n{msg}",
            )
        else:
            await bot.send_message(
                chat_id=user.chat_id, text=f"⬆️ ESCALATION ⬆️\n\n{msg}"
            )


async def check_escalation_wrapper(chat_id: str):
    db = next(get_db())
    user = get_or_create_user(db, chat_id)
    await check_escalation(db, user)


async def send_scheduled_dom_message():
    db = SessionLocal()
    user = get_or_create_user(db, USER_CHAT_ID)
    params = user.parameters
    if (
        user.safe_word_active
        and user.safe_word_until
        and datetime.utcnow() < user.safe_word_until
    ):
        return
    current_hour = datetime.utcnow().hour
    if not (params.active_hours_start <= current_hour <= params.active_hours_end):
        return
    if user.rest_day_until and datetime.utcnow() < user.rest_day_until:
        return
    prompts = [
        "I haven't spoken to my pet in a while. Remind them who owns them.",
        "Check in on my property. Demand something unexpected.",
        "My sub needs to be kept on their toes.",
        "Remind my pet what they are to me.",
        "Test my sub's devotion.",
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
            deadline=deadline,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        keyboard = [
            [InlineKeyboardButton("✓ Completed", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("✗ Failed", callback_data=f"fail_{task.id}")],
        ]
        if task_info["requires_photo"]:
            keyboard.insert(
                0,
                [
                    InlineKeyboardButton(
                        "📸 Photo Proof", callback_data=f"photo_{task.id}"
                    )
                ],
            )
        dom_msg = ConversationMessage(
            user_id=user.id, message=message, is_from_dom=True, has_avatar=True
        )
        db.add(dom_msg)
        db.commit()
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.COMMANDING, db)
        if image_data:
            await bot.send_photo(
                chat_id=USER_CHAT_ID,
                photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                caption=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await bot.send_message(
                chat_id=USER_CHAT_ID,
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        scheduler.add_job(
            lambda: asyncio.run(check_escalation_wrapper(USER_CHAT_ID)),
            trigger=IntervalTrigger(minutes=params.task_timeout_minutes),
            id=f"escalation_check_{USER_CHAT_ID}",
            replace_existing=True,
        )
    else:
        dom_msg = ConversationMessage(
            user_id=user.id,
            message=message,
            is_from_dom=True,
            message_type=MessageType.CONVERSATION.value,
            has_avatar=True,
        )
        db.add(dom_msg)
        db.commit()
        mood = random.choice(
            [AvatarMood.THOUGHTFUL, AvatarMood.WORKOUT, AvatarMood.SEDUCTIVE]
        )
        image_data = AvatarGenerator.generate_avatar(user, mood, db)
        if image_data:
            await bot.send_photo(
                chat_id=USER_CHAT_ID,
                photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                caption=message,
            )
        else:
            await bot.send_message(chat_id=USER_CHAT_ID, text=message)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """Welcome, pet. I am your Dom.

I learn. I adapt. I reward. I punish.

Commands:
/status - Your standing
/rewards - View your progress & milestones
/redeem - Spend points on rewards
/selfie - Request my image
/avatar - Customize my appearance
/analyze - Force learning analysis
/privileges - View earned perks

Obey me, and you will be rewarded. Fail me, and face consequences."""
    await update.message.reply_text(welcome)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    compliance = (
        (user.completed_tasks / user.total_tasks * 100) if user.total_tasks > 0 else 0
    )
    text = f"""
📊 Your Status, pet

Intensity: {user.intensity.upper()}
Tasks: {user.completed_tasks}/{user.total_tasks} ({compliance:.0f}%)
Current Streak: 🔥 {user.current_streak} tasks
Longest Streak: {user.longest_streak} tasks
Reward Points: ⭐ {user.reward_points}

Privileges: {', '.join(user.privileges) if user.privileges else 'None yet'}
"""
    await update.message.reply_text(text)


async def rewards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    next_milestone = None
    for threshold in sorted(RewardSystem.REWARD_THRESHOLDS.keys()):
        if threshold > user.completed_tasks:
            next_milestone = threshold
            break
    text = f"""
🏆 Your Rewards 🏆

🔥 Current Streak: {user.current_streak} tasks
📈 Longest Streak: {user.longest_streak} tasks  
✅ Total Completed: {user.completed_tasks}
⭐ Reward Points: {user.reward_points}

🎯 Next Milestone: {next_milestone} tasks
"""
    text += "\n📋 Upcoming Rewards:\n"
    for threshold, data in sorted(RewardSystem.REWARD_THRESHOLDS.items()):
        if threshold >= user.completed_tasks:
            status = "✓" if threshold <= user.completed_tasks else "○"
            text += f"{status} {threshold} tasks: {data['message'][:40]}...\n"
    recent = (
        db.query(Reward)
        .filter(Reward.user_id == user.id)
        .order_by(desc(Reward.created_at))
        .limit(3)
        .all()
    )
    if recent:
        text += "\n🎁 Recent Rewards:\n"
        for r in recent:
            text += f"• {r.description[:50]}\n"
    text += "\nUse /redeem to spend points"
    await update.message.reply_text(text)


async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    if not context.args:
        await update.message.reply_text(
            f"""💎 Redeem Points (You have: {user.reward_points}) 💎

/redeem selfie (50 pts) - Custom selfie from me
/redeem gentle (100 pts) - Reduce intensity 24h  
/redeem choice (75 pts) - Choose next task type
/redeem praise (25 pts) - Special praise message

Earn points by completing tasks and maintaining streaks."""
        )
        return
    option = context.args[0].lower()
    costs = {"selfie": 50, "gentle": 100, "choice": 75, "praise": 25}
    if option not in costs:
        await update.message.reply_text("Invalid option. Use /redeem to see options.")
        return
    if user.reward_points < costs[option]:
        await update.message.reply_text(
            f"Not enough points. You have {user.reward_points}. Complete more tasks."
        )
        return
    user.reward_points -= costs[option]
    if option == "selfie":
        mood = random.choice(
            [AvatarMood.SEDUCTIVE, AvatarMood.WORKOUT, AvatarMood.PLEASED]
        )
        image_data = AvatarGenerator.generate_avatar(user, mood, db)
        if image_data:
            await update.message.reply_photo(
                photo=InputFile(io.BytesIO(image_data), filename="dom_redeemed.jpg"),
                caption="You earned this. Enjoy it.",
            )
    elif option == "gentle":
        user.intensity = IntensityLevel.LOW.value
        await update.message.reply_text(
            "24 hours of gentleness. Don't get used to it, pet."
        )
    elif option == "choice":
        user.privileges.append("next_task_choice")
        await update.message.reply_text(
            "You may choose your next task. Reply with:\n/choose physical - for body tasks\n/choose mental - for mind tasks\n/choose service - for serving tasks"
        )
    elif option == "praise":
        msg = RewardSystem.generate_reward_message(user, "proud")
        await update.message.reply_text(f"🌟 {msg} 🌟\n\n(Redeemed with points)")
    db.commit()


async def selfie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    await update.message.reply_text("Generating my image...")
    if user.consecutive_failures > 0:
        mood = AvatarMood.DISAPPOINTED
    elif user.current_streak >= 7:
        mood = AvatarMood.SEDUCTIVE
    elif user.current_streak >= 3:
        mood = AvatarMood.PLEASED
    else:
        mood = random.choice(list(AvatarMood))
    image_data = AvatarGenerator.generate_avatar(user, mood, db)
    if image_data:
        captions = {
            AvatarMood.PLEASED: "You've been good. I approve.",
            AvatarMood.DISAPPOINTED: "I expect better from you.",
            AvatarMood.ANGRY: "You test my patience.",
            AvatarMood.COMMANDING: "Obey me.",
            AvatarMood.SEDUCTIVE: "Come closer, pet.",
            AvatarMood.WORKOUT: "This is what power looks like.",
            AvatarMood.THOUGHTFUL: "I'm considering your next test...",
            AvatarMood.DOMINANT: "You belong to me.",
        }
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(image_data), filename="dom_selfie.jpg"),
            caption=captions.get(mood, "Look at me."),
        )
    else:
        await update.message.reply_text("Image generation failed. Try again.")


async def avatar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Muscular", callback_data="avatar_build_muscular"),
            InlineKeyboardButton("Lean", callback_data="avatar_build_lean"),
        ],
        [
            InlineKeyboardButton("Dark Hair", callback_data="avatar_hair_dark"),
            InlineKeyboardButton("Light Hair", callback_data="avatar_hair_light"),
        ],
        [InlineKeyboardButton("Toggle Avatar", callback_data="avatar_toggle")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Customize how I appear to you, pet:", reply_markup=reply_markup
    )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    await update.message.reply_text("Analyzing our dynamic...")
    LearningEngine.analyze_user(db, user)
    image_data = AvatarGenerator.generate_avatar(user, AvatarMood.THOUGHTFUL, db)
    text = f"Analysis complete.\n\nRelationship Notes:\n{user.relationship_notes[:400] if user.relationship_notes else 'Still learning...'}"
    if image_data:
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(image_data), filename="dom_thinking.jpg"),
            caption=text,
        )
    else:
        await update.message.reply_text(text)


async def privileges_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    if not user.privileges:
        await update.message.reply_text("No privileges earned yet. Obey more tasks.")
        return
    privilege_descriptions = {
        "late_response": "Extra 10 minutes to complete tasks",
        "task_choice": "Can choose next task type",
        "early_release": "Can end tasks 5 minutes early",
        "photo_skip": "Can skip photo proof once per day",
    }
    text = "👑 Your Earned Privileges 👑\n\n"
    for priv in user.privileges:
        desc = privilege_descriptions.get(priv, priv)
        text += f"• {desc}\n"
    await update.message.reply_text(text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    data = query.data
    if data.startswith("avatar_"):
        if data == "avatar_toggle":
            user.parameters.avatar_enabled = not user.parameters.avatar_enabled
            db.commit()
            await query.edit_message_text(
                f"Avatar {'enabled' if user.parameters.avatar_enabled else 'disabled'}"
            )
            return
        elif data.startswith("avatar_build_"):
            user.parameters.avatar_build = data.replace("avatar_build_", "")
            db.commit()
            await query.edit_message_text(f"Build: {user.parameters.avatar_build}")
            return
        elif data.startswith("avatar_hair_"):
            user.parameters.avatar_hair = data.replace("avatar_hair_", "")
            db.commit()
            await query.edit_message_text(f"Hair: {user.parameters.avatar_hair}")
            return
    response_time = None
    if user.last_message_time:
        response_time = (datetime.utcnow() - user.last_message_time).total_seconds()
    if data.startswith("complete_"):
        task_id = int(data.split("_")[1])
        task = db.query(Task).filter(Task.id == task_id).first()
        if task and task.status == TaskStatus.PENDING.value:
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            task.user_response_time = response_time
            user.completed_tasks += 1
            user.current_streak += 1
            if user.current_streak > user.longest_streak:
                user.longest_streak = user.current_streak
            user.consecutive_failures = 0
            user.awaiting_response = False
            user.reward_points += 5
            streak_reward = RewardSystem.check_streak_rewards(user, db)
            milestone = RewardSystem.check_milestones(user, db)
            db.commit()
            if user.current_streak >= 7:
                mood = AvatarMood.SEDUCTIVE
                response_type = "seductive"
            elif user.current_streak >= 3:
                mood = AvatarMood.PLEASED
                response_type = "proud"
            else:
                mood = AvatarMood.THOUGHTFUL
                response_type = "praise"
            msg = RewardSystem.generate_reward_message(user, response_type)
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            full_message = f"✓ {msg}"
            if streak_reward:
                full_message += f"\n\n🔥 STREAK BONUS: {streak_reward.description}"
            if milestone:
                full_message += f"\n\n🎁 MILESTONE: {milestone.description}"
            if image_data:
                await query.edit_message_caption(
                    caption=f"{query.message.caption}\n\n{full_message}"
                )
            else:
                await query.edit_message_text(f"{query.message.text}\n\n{full_message}")
            if random.random() < 0.1:
                await RewardSystem.send_random_reward(user, db)
    elif data.startswith("fail_"):
        task_id = int(data.split("_")[1])
        task = db.query(Task).filter(Task.id == task_id).first()
        if task and task.status == TaskStatus.PENDING.value:
            task.status = TaskStatus.FAILED.value
            task.user_response_time = response_time
            user.failed_tasks += 1
            user.consecutive_failures += 1
            user.current_streak = 0
            user.awaiting_response = False
            user.intensity = escalate_intensity(IntensityLevel(user.intensity)).value
            db.commit()
            mood = (
                AvatarMood.ANGRY
                if user.consecutive_failures > 2
                else AvatarMood.DISAPPOINTED
            )
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            msg = generate_ai_response(user, "My pet failed me. I am displeased.", db)
            if image_data:
                await query.edit_message_caption(
                    caption=f"{query.message.caption}\n\n✗ {msg}"
                )
            else:
                await query.edit_message_text(f"{query.message.text}\n\n✗ {msg}")
    elif data.startswith("photo_"):
        task_id = int(data.split("_")[1])
        await query.edit_message_text(
            f"{query.message.text}\n\n📸 Awaiting your proof..."
        )
        context.user_data["awaiting_photo"] = task_id


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_photo" not in context.user_data:
        await process_message(update, context)
        return
    db = SessionLocal()
    user = get_or_create_user(db, str(update.effective_chat.id))
    task_id = context.user_data["awaiting_photo"]
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        task.photo_url = file.file_path
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = datetime.utcnow()
        user.completed_tasks += 1
        user.current_streak += 1
        user.consecutive_failures = 0
        user.awaiting_response = False
        user.reward_points += 5
        db.commit()
        del context.user_data["awaiting_photo"]
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.PLEASED, db)
        msg = generate_ai_response(user, "My pet sent photo proof. Good pet.", db)
        if image_data:
            await update.message.reply_photo(
                photo=InputFile(io.BytesIO(image_data), filename="dom_pleased.jpg"),
                caption=msg,
            )
        else:
            await update.message.reply_text(msg)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, is_command=False)


def schedule_next_message():
    try:
        scheduler.remove_all_jobs()
    except:
        pass
    db = next(get_db())
    user = get_or_create_user(db, USER_CHAT_ID)
    params = user.parameters
    minutes = random.randint(params.min_interval_minutes, params.max_interval_minutes)
    scheduler.add_job(
        lambda: asyncio.run(send_scheduled_dom_message()),
        trigger=IntervalTrigger(minutes=minutes),
        id="dom_message",
        replace_existing=True,
    )
    logger.info(f"Next message in {minutes} minutes")


def main():
    scheduler.start()
    schedule_next_message()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("rewards", rewards_command))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CommandHandler("selfie", selfie_command))
    application.add_handler(CommandHandler("avatar", avatar_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(CommandHandler("privileges", privileges_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
    )
    logger.info("Dom Bot started. I am watching...")
    application.run_polling()


if __name__ == "__main__":
    main()
