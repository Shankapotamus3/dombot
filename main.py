#!/usr/bin/env python3
"""
DOM Bot v6.0 - Kink Customization Edition
- 30 min timeout with punishment
- Photo retry with explanations
- Customizable kink preferences
"""

import os
import random
import asyncio
import json
import re
import io
import base64
import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from enum import Enum
from collections import defaultdict

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
import logging

import cloudinary
import cloudinary.uploader

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
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# ============================================================================
# DATABASE SETUP
# ============================================================================

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dombot.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True, 
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_timeout=30,
    pool_reset_on_return=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# ============================================================================
# ENUMS
# ============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    RELEASED = "released"

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
    DEMANDING = "demanding"
    SUSPICIOUS = "suspicious"
    EXHIBITIONIST = "exhibitionist"
    CRUEL = "cruel"
    INSPECTING = "inspecting"
    FLIRTY = "flirty"
    MOCKING = "mocking"
    CURIOUS = "curious"

class LocationType(str, Enum):
    UNKNOWN = "unknown"
    HOME = "home"
    WORK = "work"
    PUBLIC = "public"
    TRANSIT = "transit"
    SOCIAL = "social"

# ============================================================================
# DATABASE MODELS
# ============================================================================

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
    photo_demand_frequency = Column(Float, default=0.95)
    task_timeout_minutes = Column(Integer, default=30)
    escalation_threshold = Column(Integer, default=2)
    verbosity = Column(String, default="medium")
    response_delay_enabled = Column(Boolean, default=True)
    min_response_delay_seconds = Column(Integer, default=2)
    max_response_delay_seconds = Column(Integer, default=10)
    min_interval_minutes = Column(Integer, default=60)
    max_interval_minutes = Column(Integer, default=180)
    active_hours_start = Column(Integer, default=8)
    active_hours_end = Column(Integer, default=20)
    preferred_task_types = Column(JSON, default=list)
    avoided_topics = Column(JSON, default=list)
    avatar_enabled = Column(Boolean, default=True)
    avatar_frequency = Column(Float, default=0.7)
    
    avatar_style = Column(String, default="photorealistic")
    avatar_ethnicity = Column(String, default="mixed")
    avatar_nationality = Column(String, default="mediterranean")
    avatar_build = Column(String, default="muscular")
    avatar_hair = Column(String, default="dark")
    avatar_hair_length = Column(String, default="short")
    avatar_hair_color = Column(String, default="black")
    avatar_age_appearance = Column(String, default="28")
    avatar_race = Column(String, default="white")
    
    rewards_enabled = Column(Boolean, default=True)
    reward_frequency = Column(Float, default=0.1)
    check_in_frequency = Column(Integer, default=3)
    max_check_ins = Column(Integer, default=5)
    public_task_ratio = Column(Float, default=0.7)
    progressive_photo_count = Column(Integer, default=3)
    conversation_ratio = Column(Float, default=0.8)
    surprise_task_chance = Column(Float, default=0.15)
    stale_location_hours = Column(Integer, default=4)
    
    night_mode_enabled = Column(Boolean, default=True)
    night_mode_start = Column(Integer, default=20)
    night_mode_end = Column(Integer, default=8)
    
    task_creativity_level = Column(Float, default=0.8)
    risk_tolerance = Column(Float, default=0.6)
    avoid_repetition = Column(Boolean, default=True)
    
    # KINK PREFERENCES (all default to True except extreme ones)
    kink_exposure = Column(Boolean, default=True)
    kink_humiliation = Column(Boolean, default=True)
    kink_degradation = Column(Boolean, default=True)
    kink_bondage = Column(Boolean, default=True)
    kink_pain = Column(Boolean, default=False)
    kink_service = Column(Boolean, default=True)
    kink_edging = Column(Boolean, default=True)
    kink_watersports = Column(Boolean, default=False)
    kink_exhibitionism = Column(Boolean, default=True)
    kink_roleplay = Column(Boolean, default=True)
    kink_petplay = Column(Boolean, default=False)
    kink_feminization = Column(Boolean, default=False)
    kink_cbt = Column(Boolean, default=False)
    kink_breathplay = Column(Boolean, default=False)
    kink_sensory = Column(Boolean, default=True)
    kink_temperature = Column(Boolean, default=True)
    kink_marking = Column(Boolean, default=True)
    kink_spanking = Column(Boolean, default=True)
    kink_nipple = Column(Boolean, default=True)
    kink_anal = Column(Boolean, default=False)
    kink_gags = Column(Boolean, default=True)
    
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
    current_location = Column(String, default=LocationType.UNKNOWN.value)
    last_location_update = Column(DateTime, nullable=True)
    location_detail = Column(Text, nullable=True)
    
    recent_task_types = Column(JSON, default=list)
    favorite_tasks = Column(JSON, default=list)


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
    is_extended_hold = Column(Boolean, default=False)
    location_type = Column(String, default=LocationType.UNKNOWN.value)
    difficulty = Column(String, default=IntensityLevel.HIGH.value)
    ai_verified = Column(Boolean, default=False)
    ai_analysis = Column(Text, nullable=True)
    ai_generated = Column(Boolean, default=False)
    
    task_category = Column(String, default="general")
    risk_level = Column(String, default="medium")
    creativity_score = Column(Float, default=0.5)


class TaskHistory(Base):
    __tablename__ = "task_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_states.id"))
    task_description = Column(Text)
    task_hash = Column(String, index=True)
    task_category = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed = Column(Boolean, default=False)


class TaskCheckIn(Base):
    __tablename__ = "task_checkins"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    check_in_number = Column(Integer, default=1)
    sent_at = Column(DateTime, default=datetime.utcnow)
    message = Column(Text)
    requires_response = Column(Boolean, default=False)
    response_received = Column(Boolean, default=False)
    is_final = Column(Boolean, default=False)


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

# ============================================================================
# CONFIGURATION
# ============================================================================

scheduler = AsyncIOScheduler()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
VENICE_API_KEY = os.getenv("VENICE_API_KEY")
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"
SAFE_WORD = os.getenv("SAFE_WORD", "RED")

application = None

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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def truncate_for_telegram(text: str, max_length: int = 950) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def get_task_hash(description: str) -> str:
    normalized = re.sub(r'\d+', 'NUM', description.lower().strip())
    normalized = re.sub(r'[^\w\s]', '', normalized)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


# ============================================================================
# CONSTANTS
# ============================================================================

RACE_OPTIONS = {
    "white": {"description": "White / Caucasian", "prompt_addon": "white skin, Caucasian features"},
    "black": {"description": "Black / African", "prompt_addon": "black skin, African features, dark complexion"},
    "asian": {"description": "Asian", "prompt_addon": "Asian features, East Asian or Southeast Asian appearance"},
    "hispanic": {"description": "Hispanic / Latino", "prompt_addon": "Hispanic features, Latino skin tone, Latin appearance"},
    "mixed": {"description": "Mixed / Ambiguous", "prompt_addon": "mixed race features, ambiguous ethnicity"},
}

BUILD_TYPES = {
    "twink": {"description": "Twink - Slim, youthful, smooth", "prompt_addon": "very slim ectomorph build, flat toned stomach, narrow waist, youthful thin body, smooth hairless skin, slender arms, lithe frame", "gender": "young man"},
    "otter": {"description": "Otter - Slim but hairy", "prompt_addon": "slim lean build, natural body hair on chest and arms, toned but not bulky, flat stomach", "gender": "young man"},
    "jock": {"description": "Jock - Athletic, muscular", "prompt_addon": "athletic muscular build, defined abs, broad shoulders, gym-fit body", "gender": "young man"},
    "bear": {"description": "Bear - Larger, hairy", "prompt_addon": "larger stocky build, substantial chest, body hair, broad shoulders", "gender": "man"},
    "wolf": {"description": "Wolf - Muscular, hairy", "prompt_addon": "muscular athletic build, defined muscles, body hair, strong masculine features", "gender": "man"},
    "lean": {"description": "Lean - Toned, athletic", "prompt_addon": "lean toned physique, athletic build, defined but not bulky", "gender": "young man"},
    "muscular": {"description": "Muscular - Built, strong", "prompt_addon": "muscular defined physique, powerful build, strong presence", "gender": "man"},
}

HAIR_COLORS = {
    "black": "black hair", "blonde": "blonde hair", "brown": "brown hair",
    "red": "red hair", "ginger": "ginger hair", "dirty_blonde": "dirty blonde hair",
    "platinum": "platinum blonde hair", "silver": "silver hair", "bald": "bald head",
}

# ============================================================================
# KINK CATEGORIES
# ============================================================================

KINK_CATEGORIES = {
    "exposure": {
        "name": "Exposure/Nudity",
        "description": "Tasks involving nudity, stripping, revealing",
        "db_field": "kink_exposure",
        "intensity": "medium",
    },
    "humiliation": {
        "name": "Humiliation",
        "description": "Verbal degradation, embarrassing tasks",
        "db_field": "kink_humiliation",
        "intensity": "medium",
    },
    "degradation": {
        "name": "Degradation",
        "description": "Writing, marking, objectification",
        "db_field": "kink_degradation",
        "intensity": "high",
    },
    "bondage": {
        "name": "Bondage/Restraint",
        "description": "Self-bondage, holding positions, restricted movement",
        "db_field": "kink_bondage",
        "intensity": "high",
    },
    "pain": {
        "name": "Pain/Impact",
        "description": "Spanking, slapping, clamps, CBT",
        "db_field": "kink_pain",
        "intensity": "extreme",
    },
    "service": {
        "name": "Service",
        "description": "Cleaning, organizing, domestic tasks",
        "db_field": "kink_service",
        "intensity": "low",
    },
    "edging": {
        "name": "Edging/Orgasm Control",
        "description": "Stroking, denial, orgasm control",
        "db_field": "kink_edging",
        "intensity": "high",
    },
    "watersports": {
        "name": "Watersports",
        "description": "Piss play, toilet tasks",
        "db_field": "kink_watersports",
        "intensity": "extreme",
    },
    "exhibitionism": {
        "name": "Exhibitionism",
        "description": "Public risk, windows, outdoor",
        "db_field": "kink_exhibitionism",
        "intensity": "extreme",
    },
    "roleplay": {
        "name": "Roleplay",
        "description": "Scenario-based tasks, character play",
        "db_field": "kink_roleplay",
        "intensity": "medium",
    },
    "petplay": {
        "name": "Pet Play",
        "description": "Puppy, kitty, animal behaviors",
        "db_field": "kink_petplay",
        "intensity": "medium",
    },
    "feminization": {
        "name": "Feminization/Sissification",
        "description": "Wearing panties, feminine poses, makeup",
        "db_field": "kink_feminization",
        "intensity": "medium",
    },
    "cbt": {
        "name": "CBT",
        "description": "Cock and ball torture, ball busting",
        "db_field": "kink_cbt",
        "intensity": "extreme",
    },
    "breathplay": {
        "name": "Breath Play",
        "description": "Choking, breath holding, smothering",
        "db_field": "kink_breathplay",
        "intensity": "extreme",
    },
    "sensory": {
        "name": "Sensory Play",
        "description": "Blindfolds, earplugs, sensation",
        "db_field": "kink_sensory",
        "intensity": "medium",
    },
    "temperature": {
        "name": "Temperature Play",
        "description": "Ice, heat, cold exposure",
        "db_field": "kink_temperature",
        "intensity": "medium",
    },
    "marking": {
        "name": "Marking/Writing",
        "description": "Body writing, sharpie, lipstick",
        "db_field": "kink_marking",
        "intensity": "low",
    },
    "spanking": {
        "name": "Spanking",
        "description": "Self-spanking, implements, counting",
        "db_field": "kink_spanking",
        "intensity": "high",
    },
    "nipple": {
        "name": "Nipple Play",
        "description": "Clamps, twisting, stimulation",
        "db_field": "kink_nipple",
        "intensity": "medium",
    },
    "anal": {
        "name": "Anal Play",
        "description": "Plugs, fingers, prostate",
        "db_field": "kink_anal",
        "intensity": "high",
    },
    "gags": {
        "name": "Gags/Mouth",
        "description": "Gags, mouth stuffing, drool",
        "db_field": "kink_gags",
        "intensity": "medium",
    },
}

CREATIVE_FALLBACKS = [
    "Strip naked. Lie on your bed with legs up against wall. Selfie showing your face and body.",
    "Kneel on bathroom floor, forehead touching tile, naked. Mirror selfie from behind.",
    "Stand at your window, curtains open, wearing only underwear. Selfie showing outside view.",
    "Write 'OWNED' on your chest with marker. Naked selfie in mirror.",
    "Edge once, then stop. Kneel naked, hands behind back. Selfie showing your face.",
    "Bend over your bed, cheek to the surface, naked. Mirror selfie from side.",
    "Stand in front of mirror, naked, holding your phone at arm's length. Full body visible.",
    "Kneel on floor, back straight, hands behind head, naked. Selfie from above.",
]

# ============================================================================
# KINK HELPER FUNCTIONS
# ============================================================================

def get_allowed_kinks(user: UserState) -> List[str]:
    """Get list of kink categories the user has enabled"""
    params = user.parameters
    allowed = []
    
    for kink_id, kink_data in KINK_CATEGORIES.items():
        if getattr(params, kink_data['db_field'], True):
            allowed.append(kink_id)
    
    return allowed if allowed else ["exposure"]

def get_kink_status_text(user: UserState) -> str:
    """Generate status text of enabled/disabled kinks"""
    params = user.parameters
    enabled = []
    disabled = []
    
    for kink_id, kink_data in KINK_CATEGORIES.items():
        if getattr(params, kink_data['db_field'], True):
            enabled.append(kink_data['name'])
        else:
            disabled.append(kink_data['name'])
    
    text = "*ENABLED:*\n"
    text += "✅ " + "\n✅ ".join(enabled[:10])
    if len(enabled) > 10:
        text += f"\n_...and {len(enabled) - 10} more_"
    
    if disabled:
        text += "\n\n*DISABLED:*\n"
        text += "❌ " + "\n❌ ".join(disabled[:5])
        if len(disabled) > 5:
            text += f"\n_...and {len(disabled) - 5} more_"
    
    return text

# ============================================================================
# AI RESPONSE
# ============================================================================

def build_adaptive_system_prompt(user: UserState, db: Session) -> str:
    params = user.parameters
    
    base_prompt = f"""You are a Dominant in a BDSM dynamic with your submissive (called "pet").

CURRENT STATE:
- Intensity: {user.intensity}
- Streak: {user.current_streak} tasks completed
- Failures: {user.consecutive_failures} consecutive
- Points: {user.reward_points}
- Location: {user.current_location}

PERSONALITY TRAITS:
- Possessiveness: {params.possessiveness}/1.0
- Degradation: {params.degradation_level}/1.0
- Psychological focus: {params.psychological_focus}/1.0

RULES:
- Never break character as a Dominant
- Use possessive language ("my pet", "you're mine")
- Be commanding but occasionally rewarding for good behavior
- Keep responses 2-4 sentences unless asked for more
- Never use emojis
- Be unpredictable in your demands"""

    return base_prompt


def generate_ai_response(user: UserState, user_message: str, db: Session) -> str:
    logger.info("=" * 60)
    logger.info("GENERATE_AI_RESPONSE CALLED")
    logger.info("=" * 60)
    
    if not VENICE_API_KEY:
        logger.error("VENICE_API_KEY is not set!")
        return random.choice(CREATIVE_FALLBACKS)
    
    logger.info(f"VENICE_API_KEY present: {bool(VENICE_API_KEY)}")
    
    try:
        system_prompt = build_adaptive_system_prompt(user, db)
        
        history = db.query(ConversationMessage).filter(
            ConversationMessage.user_id == user.id
        ).order_by(desc(ConversationMessage.timestamp)).limit(8).all()
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in reversed(history):
            role = "assistant" if msg.is_from_dom else "user"
            messages.append({"role": role, "content": msg.message})
        
        messages.append({"role": "user", "content": user_message})
        
        logger.info(f"Sending {len(messages)} messages to Venice API")
        
        if user.parameters.response_delay_enabled:
            time.sleep(random.randint(1, 3))
        
        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 300
            },
            timeout=30,
        )
        
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"SUCCESS: {content[:100]}...")
                logger.info("=" * 60)
                return content
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.error(f"Parse error: {e}")
                return random.choice(CREATIVE_FALLBACKS)
        
        logger.error(f"API Error {response.status_code}: {response.text[:500]}")
        return random.choice(CREATIVE_FALLBACKS)
        
    except Exception as e:
        logger.error(f"Exception: {e}", exc_info=True)
        return random.choice(CREATIVE_FALLBACKS)


def generate_conversation_response(user: UserState, db: Session) -> str:
    if user.consecutive_failures > 0:
        prompt = "My pet has been disappointing me. Address them about their failures and demand better."
    elif user.current_streak >= 5:
        prompt = "My pet has been very obedient. Acknowledge their good behavior but remind them not to get complacent."
    elif user.current_location == "home":
        prompt = "Check in on my pet at home. Ask what they're doing and demand they tell you honestly."
    elif user.current_location == "work":
        prompt = "My pet is at work. Remind them who they belong to even during their professional life."
    else:
        prompt = "Initiate conversation with my pet. Ask them something intimate that reminds them of their submission."
    
    return generate_ai_response(user, prompt, db)


# ============================================================================
# PHOTO VERIFICATION
# ============================================================================

async def verify_photo_with_claude(user: UserState, task: Task, photo_bytes: bytes, db: Session) -> dict:
    cloudinary_url = None
    try:
        upload_result = cloudinary.uploader.upload(
            io.BytesIO(photo_bytes),
            folder=f"dombot/{user.chat_id}",
            public_id=f"task_{task.id}_{int(datetime.utcnow().timestamp())}",
            resource_type="auto"
        )
        cloudinary_url = upload_result.get('secure_url')
        logger.info(f"Photo uploaded: {cloudinary_url}")
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}")
    
    photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
    
    prompt = f"""You are verifying BDSM task completion. This photo is a SELFIE taken by the submissive holding their phone in ONE HAND.

TASK REQUIREMENTS:
"{task.description}"

USER CONTEXT:
- Location type: {user.current_location}
- Specific location: {user.location_detail or 'not specified'}
- Intensity level: {user.intensity}
- Time: {datetime.utcnow().strftime('%H:%M')} UTC

ANALYSIS INSTRUCTIONS:
1. Does the photo show the requested nudity/exposure level?
2. Is the position/pose as commanded?
3. Can you see their arm/hand holding the phone?
4. Does the setting match the task location?

Respond in this exact format:
VERDICT: [VERIFIED or FAILED]
CONFIDENCE: [high/medium/low]
ANALYSIS: [Your detailed explanation]

Be strict but fair. Selfies are harder to pose perfectly - focus on compliance."""

    try:
        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{photo_base64}"}}
                    ]
                }],
                "max_tokens": 800,
                "temperature": 0.2,
            },
            timeout=60,
        )
        
        if response.status_code == 200:
            result = response.json()
            analysis = result["choices"][0]["message"]["content"]
            is_verified = "VERIFIED" in analysis.upper() and "FAILED" not in analysis.upper()
            confidence = "low"
            if "high" in analysis.lower():
                confidence = "high"
            elif "medium" in analysis.lower():
                confidence = "medium"
            
            return {
                "verified": is_verified,
                "analysis": analysis,
                "cloudinary_url": cloudinary_url,
                "confidence": confidence
            }
        else:
            logger.error(f"Verification API error: {response.status_code}")
            return {
                "verified": False,
                "analysis": f"API Error: {response.status_code}",
                "cloudinary_url": cloudinary_url,
                "confidence": "none"
            }
            
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return {
            "verified": False,
            "analysis": f"Error: {str(e)}",
            "cloudinary_url": cloudinary_url,
            "confidence": "none"
        }


def get_conversational_verification_response(verified: bool, confidence: str, analysis: str, streak: int) -> str:
    if verified:
        success_intros = ["Good pet.", "That's my good boy.", "Acceptable.", "You actually listened.", "Not bad."]
        success_praises = [f"Streak now at {streak}.", f"🔥 {streak} in a row. Keep it up.", "See how easy it is when you obey?"]
        intro = random.choice(success_intros)
        praise = random.choice(success_praises)
        if confidence == "low":
            return f"{intro}\n\n{praise}\n\n(Your photo was a bit unclear, but I'll allow it.)"
        return f"{intro}\n\n{praise}"
    else:
        failure_intros = ["Disappointing.", "That won't do at all.", "Did you think I wouldn't notice?", "Unacceptable."]
        failure_reactions = ["Streak broken. Back to zero.", "Points deducted. Try harder next time.", "I'll remember this failure."]
        intro = random.choice(failure_intros)
        reaction = random.choice(failure_reactions)
        return f"{intro}\n\n{reaction}"


# ============================================================================
# TASK GENERATION WITH KINKS
# ============================================================================

def get_recent_task_hashes(db: Session, user_id: int, hours: int = 48) -> Set[str]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    recent = db.query(TaskHistory).filter(TaskHistory.user_id == user_id, TaskHistory.created_at > cutoff).all()
    return {t.task_hash for t in recent}


async def generate_creative_ai_task(user: UserState, db: Session) -> dict:
    location = user.current_location or "unknown"
    location_detail = user.location_detail or ""
    time_of_day = (datetime.utcnow() - timedelta(hours=7)).hour
    intensity = user.intensity
    creativity = user.parameters.task_creativity_level
    risk_tolerance = user.parameters.risk_tolerance
    
    if 5 <= time_of_day < 12:
        time_period = "morning"
    elif 12 <= time_of_day < 17:
        time_period = "afternoon"
    elif 17 <= time_of_day < 22:
        time_period = "evening"
    else:
        time_period = "night"
    
    # GET ALLOWED KINKS FOR THIS USER
    allowed_kinks = get_allowed_kinks(user)
    recent_hashes = get_recent_task_hashes(db, user.id)
    
    # Filter by intensity preference
    preferred = []
    if intensity == IntensityLevel.EXTREME.value:
        preferred = [k for k in allowed_kinks if KINK_CATEGORIES[k]['intensity'] in ['high', 'extreme']]
    elif intensity == IntensityLevel.HIGH.value:
        preferred = [k for k in allowed_kinks if KINK_CATEGORIES[k]['intensity'] in ['medium', 'high', 'extreme']]
    else:
        preferred = allowed_kinks
    
    # Select from allowed kinks
    if preferred and random.random() < creativity:
        selected_category = random.choice(preferred)
    else:
        selected_category = random.choice(allowed_kinks) if allowed_kinks else "exposure"
    
    kink_info = KINK_CATEGORIES[selected_category]
    
    risk_level = "medium"
    if risk_tolerance > 0.8 or intensity == IntensityLevel.EXTREME.value:
        risk_level = "extreme"
    elif risk_tolerance > 0.6 or intensity == IntensityLevel.HIGH.value:
        risk_level = "high"
    
    recent_tasks = db.query(TaskHistory).filter(TaskHistory.user_id == user.id).order_by(desc(TaskHistory.created_at)).limit(5).all()
    recent_descriptions = [t.task_description for t in recent_tasks]
    recent_text = "\n".join([f"- {d}" for d in recent_descriptions]) if recent_descriptions else "None yet."
    
    prompt = f"""Create a UNIQUE, CREATIVE BDSM task focused on: {kink_info['name']}

KINK FOCUS: {kink_info['description']}

CRITICAL RULES:
1. The photo MUST be a SELFIE taken by the submissive holding their phone in ONE HAND
2. Be SPECIFIC and CREATIVE - use exact furniture, rooms, objects
3. Make it CHALLENGING but physically possible as a selfie
4. NEVER repeat these recent tasks:
{recent_text}

TASK CATEGORY: {selected_category.upper()}
RISK LEVEL: {risk_level}
INTENSITY: {intensity}

CONTEXT:
- Location: {location} ({location_detail if location_detail else 'use creative specifics'})
- Time: {time_period}
- Creativity Level: {creativity}/1.0

SELFIE CONSTRAINTS:
- One hand holds phone (arm may be visible)
- Limited to arm's reach or mirrors
- No impossible angles

Example tasks:
- "Strip naked. Lie on your bed with legs up against wall. Selfie showing your face and feet."
- "Kneel on bathroom floor, forehead touching tile, naked. Mirror selfie from behind."

Create something UNIQUE:

TASK:"""

    try:
        ai_description = generate_ai_response(user, prompt, db)
        ai_description = ai_description.strip().strip('"\'')
        
        if len(ai_description) > 350:
            ai_description = ai_description[:347] + "..."
        
        if "photo" not in ai_description.lower() and "selfie" not in ai_description.lower():
            ai_description += " Selfie proof."
        
        task_hash = get_task_hash(ai_description)
        if task_hash in recent_hashes and user.parameters.avoid_repetition:
            logger.info("Task too similar, regenerating...")
            prompt += "\n\nWARNING: The above task was too similar to a recent one. Create something COMPLETELY DIFFERENT."
            ai_description = generate_ai_response(user, prompt, db)
            ai_description = ai_description.strip().strip('"\'')
            if len(ai_description) > 350:
                ai_description = ai_description[:347] + "..."
        
        is_extended_hold = any(phrase in ai_description.lower() for phrase in ["until i say", "do not move", "hold position", "wait for", "kneel until", "hold for"])
        
        task_history = TaskHistory(
            user_id=user.id,
            task_description=ai_description,
            task_hash=get_task_hash(ai_description),
            task_category=selected_category
        )
        db.add(task_history)
        
        recent_types = user.recent_task_types or []
        recent_types.append(selected_category)
        user.recent_task_types = recent_types[-10:]
        
        db.commit()
        
        return {
            "description": ai_description,
            "task_type": f"{selected_category}_{location}",
            "requires_photo": True,
            "is_extended_hold": is_extended_hold,
            "location_type": location,
            "difficulty": intensity,
            "ai_generated": True,
            "task_category": selected_category,
            "risk_level": risk_level,
            "creativity_score": creativity,
        }
        
    except Exception as e:
        logger.error(f"AI task generation failed: {e}")
        # Pick from allowed kinks for fallback
        allowed = get_allowed_kinks(user)
        fallback_category = random.choice(allowed) if allowed else "exposure"
        fallback = random.choice(CREATIVE_FALLBACKS)
        return {
            "description": fallback,
            "task_type": fallback_category,
            "requires_photo": True,
            "is_extended_hold": False,
            "location_type": location,
            "difficulty": intensity,
            "ai_generated": False,
            "task_category": fallback_category,
            "risk_level": "medium",
            "creativity_score": 0.5,
        }


async def get_smart_task_for_user(user: UserState, db: Session) -> dict:
    params = user.parameters
    has_details = user.location_detail and len(user.location_detail) > 3
    use_ai = has_details or random.random() < (0.7 + params.task_creativity_level * 0.3)
    
    if use_ai:
        return await generate_creative_ai_task(user, db)
    else:
        location = user.current_location or "home"
        # Filter templates by allowed kinks
        allowed = get_allowed_kinks(user)
        
        templates = {
            "exposure": [
                "Strip naked. Lie on your back on the floor, legs up the wall. Selfie showing your face and body.",
                "Naked in front of your open window, back to the glass. Selfie in mirror showing the view.",
                "Kneel on your bed, face down, ass up. Mirror selfie from behind.",
            ],
            "degradation": [
                "Write 'SLAVE' on your chest with marker. Naked selfie in mirror.",
                "Kneel naked with 'PROPERTY' written on your forehead. Mirror selfie.",
            ],
            "position": [
                "Hold plank position naked. Selfie from below showing your strain.",
                "Wall sit position, naked, back against wall. Selfie showing your face.",
            ],
            "service": [
                "Clean your floor naked on hands and knees. Selfie from behind.",
                "Kneel naked beside your bed, making it perfectly. Mirror selfie.",
            ],
        }
        
        # Only use templates from allowed kinks
        available_templates = []
        for kink, temps in templates.items():
            if kink in allowed:
                available_templates.extend(temps)
        
        if not available_templates:
            available_templates = templates["exposure"]  # Fallback
        
        template = random.choice(available_templates)
        
        return {
            "description": template,
            "task_type": location,
            "requires_photo": True,
            "is_extended_hold": False,
            "location_type": location,
            "difficulty": user.intensity,
            "ai_generated": False,
            "task_category": "template",
            "risk_level": "medium",
            "creativity_score": 0.3,
        }


async def expire_old_tasks(user: UserState, db: Session):
    """Clear expired tasks - no punishment, just cleanup"""
    cutoff = datetime.utcnow() - timedelta(minutes=user.parameters.task_timeout_minutes + 5)
    
    old_tasks = db.query(Task).filter(
        Task.user_id == user.id, 
        Task.status == TaskStatus.PENDING.value, 
        Task.created_at < cutoff
    ).all()
    
    for task in old_tasks:
        task.status = TaskStatus.EXPIRED.value
        logger.info(f"Task {task.id} expired (auto-cleared)")
    
    if user.current_task_id:
        current_task = db.query(Task).filter(Task.id == user.current_task_id).first()
        if not current_task or current_task.status in [
            TaskStatus.COMPLETED.value, 
            TaskStatus.FAILED.value, 
            TaskStatus.EXPIRED.value, 
            TaskStatus.RELEASED.value
        ]:
            user.current_task_id = None
            user.awaiting_response = False
            logger.info(f"Cleared stale task for user {user.id}")
    
    db.commit()


# ============================================================================
# AVATAR GENERATOR
# ============================================================================

class AvatarGenerator:
    MOOD_PROMPTS = {
        AvatarMood.COMMANDING: {"description": "standing tall, arms crossed, intense eye contact, powerful stance", "clothing": "tight black briefs or jockstrap, harness", "expression": "intense, commanding", "setting": "minimalist dark room, dramatic lighting"},
        AvatarMood.PLEASED: {"description": "slight confident smile, relaxed posture, approving look", "clothing": "unbuttoned shirt or briefs showing physique", "expression": "satisfied, proud", "setting": "bedroom or private gym"},
        AvatarMood.DISAPPOINTED: {"description": "crossed arms, head tilted, looking down", "clothing": "formal wear or leather", "expression": "disappointed, stern", "setting": "office or dungeon"},
        AvatarMood.ANGRY: {"description": "fists clenched, leaning forward, aggressive", "clothing": "sweat-soaked tank or bare chest", "expression": "angry, furious", "setting": "gym, harsh lighting"},
        AvatarMood.THOUGHTFUL: {"description": "sitting, contemplative, calculating", "clothing": "casual, sweatpants low, bare torso", "expression": "thoughtful, scheming", "setting": "private study"},
        AvatarMood.SEDUCTIVE: {"description": "reclining, inviting but dominant", "clothing": "minimal - briefs or towel", "expression": "seductive, tempting", "setting": "luxury bedroom"},
        AvatarMood.DOMINANT: {"description": "standing over, power pose, ownership", "clothing": "leather harness, chaps, boots", "expression": "possessive, dominant", "setting": "dungeon or throne"},
        AvatarMood.WORKOUT: {"description": "sweaty post-workout, muscles pumped, glistening", "clothing": "tight compression shorts", "expression": "intense, focused", "setting": "gym or locker room"},
        AvatarMood.DEMANDING: {"description": "close-up, intense stare, finger pointing", "clothing": "unzipped pants, bare chest", "expression": "demanding, impatient", "setting": "dimly lit room"},
        AvatarMood.SUSPICIOUS: {"description": "squinting, head tilted, examining", "clothing": "open shirt", "expression": "suspicious, scrutinizing", "setting": "office with harsh lighting"},
        AvatarMood.EXHIBITIONIST: {"description": "outdoors or public space, confident pose", "clothing": "minimal - thong, harness", "expression": "bold, daring", "setting": "alleyway or public bathroom"},
        AvatarMood.CRUEL: {"description": "towering angle, mocking smirk", "clothing": "full leather, boots", "expression": "cruel, mocking", "setting": "dungeon, chains visible"},
        AvatarMood.INSPECTING: {"description": "holding phone, examining intently", "clothing": "casual, robe partially open", "expression": "critical, evaluating", "setting": "private quarters"},
        AvatarMood.FLIRTY: {"description": "playful pose, winking or smirking", "clothing": "casual, shirt unbuttoned", "expression": "flirty, playful", "setting": "cozy bedroom"},
        AvatarMood.MOCKING: {"description": "laughing dismissively, confident posture", "clothing": "dominant attire", "expression": "mocking, superior", "setting": "throne"},
        AvatarMood.CURIOUS: {"description": "leaning forward, interested expression", "clothing": "casual, approachable", "expression": "curious, intrigued", "setting": "intimate setting"},
    }

    @staticmethod
    def build_prompt(user: UserState, mood: AvatarMood) -> str:
        params = user.parameters
        mood_data = AvatarGenerator.MOOD_PROMPTS.get(mood, AvatarGenerator.MOOD_PROMPTS[AvatarMood.COMMANDING])
        
        race = getattr(params, 'avatar_race', 'white')
        race_descriptor = {"white": "white skin, Caucasian", "black": "black skin, African", "asian": "Asian features", "hispanic": "Hispanic, Latino", "mixed": "mixed race"}.get(race, "Caucasian")
        
        hair_color = getattr(params, 'avatar_hair_color', 'black')
        hair_desc = HAIR_COLORS.get(hair_color, "black hair")
        
        build_type = getattr(params, 'avatar_build', 'muscular')
        build_info = BUILD_TYPES.get(build_type, BUILD_TYPES['muscular'])
        
        physical = f"{params.avatar_age_appearance}-year-old {build_info['gender']}, {race_descriptor}, {build_info['prompt_addon']}, {hair_desc}"
        
        prompt = f"{params.avatar_style} photograph of a dominant {physical}, {mood_data['description']}, {mood_data['clothing']}, {mood_data['expression']}, {mood_data['setting']}, highly detailed, professional lighting, 4k quality, full body visible head to toe"
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
                    "height": 512,
                    "seed": random.randint(1, 1000000)
                },
                timeout=30,
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
        elif context == "conversation":
            return random.choice([AvatarMood.THOUGHTFUL, AvatarMood.FLIRTY, AvatarMood.CURIOUS])
        elif user.intensity == IntensityLevel.EXTREME.value:
            return AvatarMood.DOMINANT
        else:
            return AvatarMood.COMMANDING


# ============================================================================
# CORE LOGIC
# ============================================================================

def check_understanding_mode(user_message: str) -> bool:
    refusal = ["can't", "cannot", "impossible", "too risky", "refuse", "scared", "not safe", "unable", "won't"]
    return any(r in user_message.lower() for r in refusal)


def offer_alternative_task(user: UserState, original_task: Task, db: Session) -> dict:
    alternatives = {
        "exposure": "ALTERNATIVE: Keep underwear on, but pull them down in back. Mirror selfie from behind. -10 points.",
        "position": "ALTERNATIVE: Same position but fully clothed. Still take the selfie. -15 points.",
        "public_risk": "ALTERNATIVE: Do it in private but with curtains open. Same pose. -20 points.",
        "degradation": "ALTERNATIVE: Write the word smaller, on your thigh instead. -10 points.",
        "edging": "ALTERNATIVE: Just hold the position without edging. Fully clothed. -15 points.",
    }
    
    category = getattr(original_task, 'task_category', 'general')
    alt_desc = alternatives.get(category, "ALTERNATIVE: Strip to underwear only. Selfie in mirror. -15 points.")
    
    return {
        "description": alt_desc,
        "task_type": "alternative",
        "requires_photo": True,
        "is_extended_hold": False,
        "location_type": original_task.location_type,
        "difficulty": IntensityLevel.HIGH.value,
        "ai_generated": False,
    }


# ============================================================================
# MESSAGE HANDLERS
# ============================================================================

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_command: bool = False):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        params = user.parameters
        
        await expire_old_tasks(user, db)
        
        # Night mode check
        if params.night_mode_enabled:
            current_hour = (datetime.utcnow() - timedelta(hours=7)).hour
            if current_hour >= params.night_mode_start or current_hour < params.night_mode_end:
                if update.message.text:
                    ai_response = generate_ai_response(user, update.message.text, db)
                    await update.message.reply_text(f"🌙 Night Mode. {ai_response}")
                return
        
        user_text = update.message.text if update.message.text else "[image]"
        
        # Check understanding mode FIRST
        if user.current_task_id and check_understanding_mode(user_text):
            task = db.query(Task).filter(Task.id == user.current_task_id).first()
            if task and task.status == TaskStatus.PENDING.value:
                alt = offer_alternative_task(user, task, db)
                task.status = TaskStatus.FAILED.value
                user.failed_tasks += 1
                user.reward_points = max(0, user.reward_points - 15)
                db.commit()
                await update.message.reply_text(f"😈 MERCY:\n\n{alt['description']}")
                return
        
        # Log message
        user_msg = ConversationMessage(user_id=user.id, message=user_text, is_from_dom=False)
        db.add(user_msg)
        user.interaction_count += 1
        db.commit()
        
        # Only check stale location if NO active task
        if user.last_location_update and not user.current_task_id:
            hours_since = (datetime.utcnow() - user.last_location_update).total_seconds() / 3600
            if hours_since > params.stale_location_hours and not is_command:
                keyboard = [
                    [InlineKeyboardButton("🏠 Home", callback_data="loc_home")],
                    [InlineKeyboardButton("💼 Work", callback_data="loc_work")],
                ]
                await update.message.reply_text(
                    f"📍 Location stale ({int(hours_since)}h). Update?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
        
        # Check if user has active task before generating new one
        if user.current_task_id:
            task = db.query(Task).filter(Task.id == user.current_task_id).first()
            if task and task.status == TaskStatus.PENDING.value:
                time_left = task.deadline - datetime.utcnow()
                minutes_left = max(0, int(time_left.total_seconds() / 60))
                await update.message.reply_text(
                    f"⏳ Finish your current task first! ({minutes_left}m left)\n"
                    f"Complete it or use /release to give up (-20 points)!"
                )
                return
        
        # Higher chance of conversation
        is_question = "?" in user_text or any(word in user_text.lower() for word in ["what", "how", "why", "when", "where", "who", "can you", "will you"])
        is_conversation = random.random() < params.conversation_ratio or is_question
        
        if is_conversation and not is_command:
            ai_response = generate_ai_response(user, user_text, db)
            dom_msg = ConversationMessage(user_id=user.id, message=ai_response, is_from_dom=True)
            db.add(dom_msg)
            db.commit()
            
            if random.random() < params.avatar_frequency:
                image_data = AvatarGenerator.generate_avatar(user, AvatarGenerator.determine_mood(user, "conversation"), db)
                if image_data:
                    await update.message.reply_photo(
                        photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"),
                        caption=ai_response,
                    )
                else:
                    await update.message.reply_text(ai_response)
            else:
                await update.message.reply_text(ai_response)
            return
        
        # Generate AI task
        task_data = await get_smart_task_for_user(user, db)
        
        deadline = datetime.utcnow() + timedelta(minutes=params.task_timeout_minutes)
        task = Task(
            user_id=user.id,
            description=task_data["description"],
            task_type=task_data["task_type"],
            requires_photo=True,
            intensity=task_data["difficulty"],
            deadline=deadline,
            is_extended_hold=task_data.get("is_extended_hold", False),
            location_type=task_data.get("location_type", user.current_location),
            ai_generated=task_data.get("ai_generated", False),
            task_category=task_data.get("task_category", "general"),
            risk_level=task_data.get("risk_level", "medium"),
            creativity_score=task_data.get("creativity_score", 0.5),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        
        keyboard = [
            [InlineKeyboardButton("✓ Complete", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("✗ Fail", callback_data=f"fail_{task.id}")],
        ]
        
        ai_badge = "🤖 " if task_data.get("ai_generated") else ""
        description = truncate_for_telegram(task_data['description'], 600)
        full_message = truncate_for_telegram(
            f"{ai_badge}📋 TASK:\n{description}\n\n⏰ You have 30 minutes to complete.\n\n📸 SELFIE REQUIRED",
            950
        )
        
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.COMMANDING, db)
        
        if image_data:
            await update.message.reply_photo(
                photo=InputFile(io.BytesIO(image_data), filename="task.jpg"),
                caption=full_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await update.message.reply_text(full_message, reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Schedule task auto-clear with punishment after 30 minutes
        timeout_minutes = params.task_timeout_minutes
        chat_id = str(update.effective_chat.id)
        task_id = task.id
        
        async def auto_clear_task_with_punishment():
            """Auto-clear task after timeout with punishment"""
            await asyncio.sleep(timeout_minutes * 60)
            db2 = SessionLocal()
            try:
                user2 = get_or_create_user(db2, chat_id)
                task2 = db2.query(Task).filter(Task.id == task_id).first()
                
                if task2 and task2.status == TaskStatus.PENDING.value:
                    task2.status = TaskStatus.EXPIRED.value
                    user2.failed_tasks += 1
                    user2.consecutive_failures += 1
                    user2.current_streak = 0
                    user2.reward_points = max(0, user2.reward_points - 10)
                    user2.current_task_id = None
                    user2.awaiting_response = False
                    db2.commit()
                    
                    punishments = [
                        "⏰ Task expired. You took too long. -10 points. Don't let it happen again.",
                        "⏰ Time's up, pet. You failed me. -10 points. Streak broken.",
                        "⏰ 30 minutes passed. Task expired. -10 points. Disappointing.",
                        "⏰ You kept me waiting too long. Task cancelled. -10 points.",
                    ]
                    
                    if application and application.bot:
                        await application.bot.send_message(
                            chat_id=chat_id,
                            text=random.choice(punishments)
                        )
                    logger.info(f"Task {task_id} expired with punishment")
                    
            except Exception as e:
                logger.error(f"Auto-clear error: {e}")
            finally:
                db2.close()
        
        asyncio.create_task(auto_clear_task_with_punishment())
                
    except Exception as e:
        logger.error(f"Process message error: {e}", exc_info=True)
    finally:
        db.close()


async def enhanced_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        await expire_old_tasks(user, db)
        
        task_id = context.user_data.get("awaiting_photo_task_id")
        
        if not task_id:
            await process_message(update, context)
            return
        
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await update.message.reply_text("Task not found.")
            return
        
        if not update.message.photo:
            await update.message.reply_text("No photo detected.")
            return
        
        is_retry = context.user_data.get("photo_retry_count", 0) > 0
        
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        
        analyzing_msg = await update.message.reply_text("🔍 Examining your submission...")
        
        verification = await verify_photo_with_claude(user, task, photo_bytes, db)
        
        task.ai_analysis = verification["analysis"]
        task.ai_verified = verification["verified"]
        
        await analyzing_msg.delete()
        
        if verification["verified"]:
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            user.completed_tasks += 1
            user.current_streak += 1
            user.consecutive_failures = 0
            user.awaiting_response = False
            user.reward_points += 5
            user.current_task_id = None
            
            context.user_data.pop("photo_retry_count", None)
            context.user_data.pop("awaiting_photo_type", None)
            context.user_data.pop("awaiting_photo_task_id", None)
            
            favorites = user.favorite_tasks or []
            favorites.append(getattr(task, 'task_category', 'general'))
            user.favorite_tasks = favorites[-10:]
            
            response_text = get_conversational_verification_response(True, verification['confidence'], verification['analysis'], user.current_streak)
            
            image_data = AvatarGenerator.generate_avatar(user, AvatarMood.PLEASED, db)
            if image_data:
                await update.message.reply_photo(photo=InputFile(io.BytesIO(image_data), filename="approved.jpg"), caption=response_text)
            else:
                await update.message.reply_text(response_text)
            
            db.commit()
            
        else:
            retry_count = context.user_data.get("photo_retry_count", 0)
            
            if retry_count == 0:
                context.user_data["photo_retry_count"] = 1
                
                analysis = verification['analysis']
                reason = "Photo did not meet requirements."
                
                if "clothed" in analysis.lower() or "clothing" in analysis.lower():
                    reason = "❌ You were supposed to be naked/less clothed."
                elif "pose" in analysis.lower() or "position" in analysis.lower():
                    reason = "❌ Your position/pose was incorrect."
                elif "location" in analysis.lower():
                    reason = "❌ Wrong location or setting."
                elif "angle" in analysis.lower() or "selfie" in analysis.lower():
                    reason = "❌ Photo angle or selfie technique was wrong."
                elif "lighting" in analysis.lower() or "dark" in analysis.lower():
                    reason = "❌ Photo too dark or poor lighting."
                elif "blurry" in analysis.lower() or "unclear" in analysis.lower():
                    reason = "❌ Photo was blurry or unclear."
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Try Again", callback_data=f"retry_photo_{task_id}")],
                    [InlineKeyboardButton("✗ Give Up", callback_data=f"fail_{task_id}")],
                ]
                
                message = (
                    f"❌ VERIFICATION FAILED\n\n"
                    f"**Why:** {reason}\n\n"
                    f"**Details:** {truncate_for_telegram(analysis, 300)}\n\n"
                    f"⚠️ This is your **second chance**. Fix the issue and send a new photo, "
                    f"or give up (-10 points, streak broken)."
                )
                
                image_data = AvatarGenerator.generate_avatar(user, AvatarMood.SUSPICIOUS, db)
                if image_data:
                    await update.message.reply_photo(
                        photo=InputFile(io.BytesIO(image_data), filename="suspicious.jpg"),
                        caption=message,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
                
                db.commit()
                
            else:
                task.status = TaskStatus.FAILED.value
                user.failed_tasks += 1
                user.consecutive_failures += 1
                user.current_streak = 0
                user.awaiting_response = False
                user.reward_points = max(0, user.reward_points - 10)
                user.current_task_id = None
                
                context.user_data.pop("photo_retry_count", None)
                context.user_data.pop("awaiting_photo_type", None)
                context.user_data.pop("awaiting_photo_task_id", None)
                
                response_text = (
                    f"❌ FAILED - Second attempt rejected.\n\n"
                    f"**Analysis:** {truncate_for_telegram(verification['analysis'], 200)}\n\n"
                    f"Streak broken. -10 points. Try harder next time."
                )
                
                image_data = AvatarGenerator.generate_avatar(user, AvatarMood.DISAPPOINTED, db)
                if image_data:
                    await update.message.reply_photo(photo=InputFile(io.BytesIO(image_data), filename="disappointed.jpg"), caption=response_text)
                else:
                    await update.message.reply_text(response_text)
                
                db.commit()
            
    except Exception as e:
        logger.error(f"Photo handler error: {e}", exc_info=True)
        await update.message.reply_text("Error processing photo.")
    finally:
        db.close()


# ============================================================================
# BUTTON CALLBACK
# ============================================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        await expire_old_tasks(user, db)
        
        data = query.data
        
        # Handle kink toggles
        if data.startswith("kink_toggle_"):
            kink_id = data.replace("kink_toggle_", "")
            if kink_id in KINK_CATEGORIES:
                field = KINK_CATEGORIES[kink_id]['db_field']
                current = getattr(user.parameters, field, True)
                setattr(user.parameters, field, not current)
                db.commit()
                
                # Refresh display
                await display_kinks_menu(update, context, user)
            return
        
        if data == "kink_reset_on":
            for kink_data in KINK_CATEGORIES.values():
                setattr(user.parameters, kink_data['db_field'], True)
            db.commit()
            await query.answer("All kinks enabled")
            await display_kinks_menu(update, context, user)
            return
        
        if data == "kink_reset_off":
            for kink_data in KINK_CATEGORIES.values():
                setattr(user.parameters, kink_data['db_field'], False)
            db.commit()
            await query.answer("All kinks disabled")
            await display_kinks_menu(update, context, user)
            return
        
        if data.startswith("loc_"):
            location_map = {"loc_home": LocationType.HOME, "loc_work": LocationType.WORK, "loc_public": LocationType.PUBLIC, "loc_transit": LocationType.TRANSIT}
            new_loc = location_map.get(data, LocationType.UNKNOWN)
            user.current_location = new_loc.value
            user.last_location_update = datetime.utcnow()
            db.commit()
            await query.edit_message_text(f"📍 {new_loc.value}\n\nUse /locationdetail")
            return
        
        elif data.startswith("avatar_race_"):
            race = data.replace("avatar_race_", "")
            context.user_data['selected_race'] = race
            keyboard = [
                [InlineKeyboardButton("Twink", callback_data="avatar_build_twink"), InlineKeyboardButton("Otter", callback_data="avatar_build_otter")],
                [InlineKeyboardButton("Jock", callback_data="avatar_build_jock"), InlineKeyboardButton("Bear", callback_data="avatar_build_bear")],
                [InlineKeyboardButton("Wolf", callback_data="avatar_build_wolf"), InlineKeyboardButton("Lean", callback_data="avatar_build_lean")],
                [InlineKeyboardButton("Muscular", callback_data="avatar_build_muscular")],
            ]
            await query.edit_message_text(f"Race: {race.title()}\n\nChoose build:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        elif data.startswith("avatar_build_"):
            build = data.replace("avatar_build_", "")
            race = context.user_data.get('selected_race', 'white')
            user.parameters.avatar_build = build
            user.parameters.avatar_race = race
            db.commit()
            keyboard = [
                [InlineKeyboardButton("Black", callback_data="hair_black"), InlineKeyboardButton("Blonde", callback_data="hair_blonde")],
                [InlineKeyboardButton("Brown", callback_data="hair_brown"), InlineKeyboardButton("Red", callback_data="hair_red")],
                [InlineKeyboardButton("Ginger", callback_data="hair_ginger"), InlineKeyboardButton("Dirty Blonde", callback_data="hair_dirty_blonde")],
                [InlineKeyboardButton("Platinum", callback_data="hair_platinum"), InlineKeyboardButton("Silver", callback_data="hair_silver")],
                [InlineKeyboardButton("Bald", callback_data="hair_bald")],
            ]
            await query.edit_message_text(f"Set: {race.title()} {build}\n\nHair color:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        elif data.startswith("hair_"):
            color = data.replace("hair_", "")
            user.parameters.avatar_hair_color = color
            db.commit()
            await query.edit_message_text(f"✅ Avatar set: {user.parameters.avatar_race.title()} {user.parameters.avatar_build} with {HAIR_COLORS.get(color, color)}")
            return
        
        elif data == "avatar_toggle":
            user.parameters.avatar_enabled = not user.parameters.avatar_enabled
            db.commit()
            await query.edit_message_text(f"Avatar: {'on' if user.parameters.avatar_enabled else 'off'}")
            return
        
        # Handle Retry Photo button
        if data.startswith("retry_photo_"):
            task_id = int(data.split("_")[2])
            task = db.query(Task).filter(Task.id == task_id).first()
            
            if not task or task.status != TaskStatus.PENDING.value:
                await query.answer("Task no longer active.")
                return
            
            context.user_data["awaiting_photo_type"] = "task_completion"
            context.user_data["awaiting_photo_task_id"] = task_id
            
            await query.answer("Send your new photo")
            
            try:
                if query.message.caption:
                    await query.edit_message_caption(
                        caption="📸 **SECOND CHANCE**\n\nSend your corrected photo now. Get it right this time.",
                        parse_mode='Markdown'
                    )
                elif query.message.text:
                    await query.edit_message_text(
                        text="📸 **SECOND CHANCE**\n\nSend your corrected photo now. Get it right this time.",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                await update.effective_chat.send_message("📸 Send your corrected photo.")
            
            return
        
        # Handle Complete button
        if data.startswith("complete_"):
            task_id = int(data.split("_")[1])
            task = db.query(Task).filter(Task.id == task_id).first()
            
            if not task:
                await query.edit_message_text("Task not found.")
                return
                
            if task.status != TaskStatus.PENDING.value:
                await query.edit_message_text("This task is no longer active.")
                return
            
            context.user_data["awaiting_photo_type"] = "task_completion"
            context.user_data["awaiting_photo_task_id"] = task_id
            
            try:
                if query.message.caption:
                    new_caption = truncate_for_telegram(f"{query.message.caption}\n\n📸 Send your selfie now!", 950)
                    await query.edit_message_caption(caption=new_caption)
                elif query.message.text:
                    new_text = truncate_for_telegram(f"{query.message.text}\n\n📸 Send your selfie now!", 950)
                    await query.edit_message_text(text=new_text)
                else:
                    await query.answer("📸 Send selfie to complete!")
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")
                await query.answer("📸 Send selfie to complete!")
            return
        
        # Handle Fail button
        if data.startswith("fail_"):
            task_id = int(data.split("_")[1])
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED.value
                user.failed_tasks += 1
                user.consecutive_failures += 1
                user.current_streak = 0
                user.awaiting_response = False
                user.current_task_id = None
                db.commit()
                await query.edit_message_text("❌ FAILED")
            return
        
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        try:
            await query.answer("Error processing. Try again.")
        except:
            pass
    finally:
        db.close()


# ============================================================================
# COMMANDS
# ============================================================================

async def display_kinks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user: UserState = None):
    """Display kink settings menu"""
    if user is None:
        db = SessionLocal()
        try:
            user = get_or_create_user(db, str(update.effective_chat.id))
        finally:
            db.close()
    
    params = user.parameters
    
    keyboard = []
    row = []
    
    for kink_id, kink_data in KINK_CATEGORIES.items():
        enabled = getattr(params, kink_data['db_field'], True)
        status = "✅" if enabled else "❌"
        
        button = InlineKeyboardButton(
            f"{status} {kink_data['name']}",
            callback_data=f"kink_toggle_{kink_id}"
        )
        row.append(button)
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔄 Enable All", callback_data="kink_reset_on")])
    keyboard.append([InlineKeyboardButton("⛔ Disable All", callback_data="kink_reset_off")])
    
    text = (
        "*KINK SETTINGS*\n\n"
        "Toggle kinks on/off. Only enabled kinks will appear in tasks.\n\n"
        f"{get_kink_status_text(user)}\n\n"
        "Use `/kinks [name]` to toggle by text\n"
        "Example: `/kinks pain`"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome, pet.\n\n/status - Standing\n/location - Set location\n/locationdetail - Be specific\n/kinks - Customize kinks\n/nightmode - Toggle night\n/selfie - My image\n/avatar - Customize me\n/setfrequency - How often I message\n/setcreativity - How daring (0-1)\n/setrisk - Risk tolerance (0-1)\n/release - Give up task\n/debug - Test AI connection"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        loc_detail = f" ({user.location_detail})" if user.location_detail else ""
        race = getattr(user.parameters, 'avatar_race', 'white')
        hair = getattr(user.parameters, 'avatar_hair_color', 'black')
        
        current_task_info = ""
        if user.current_task_id:
            task = db.query(Task).filter(Task.id == user.current_task_id).first()
            if task and task.status == TaskStatus.PENDING.value:
                time_left = task.deadline - datetime.utcnow()
                minutes_left = max(0, int(time_left.total_seconds() / 60))
                current_task_info = f"\n⏳ Active task: {minutes_left}m left"
            else:
                current_task_info = "\n✅ No active task"
        
        # Count enabled kinks
        enabled_count = len(get_allowed_kinks(user))
        
        text = f"""
📊 Status
Location: {user.current_location}{loc_detail}
Avatar: {race.title()} {user.parameters.avatar_build}, {HAIR_COLORS.get(hair, hair)}
Tasks: {user.completed_tasks}/{user.total_tasks}
Streak: 🔥 {user.current_streak}
Points: ⭐ {user.reward_points}
Timeout: {user.parameters.task_timeout_minutes} min | Frequency: {user.parameters.min_interval_minutes}-{user.parameters.max_interval_minutes} min
Creativity: {user.parameters.task_creativity_level:.1f} | Risk: {user.parameters.risk_tolerance:.1f}
Kinks: {enabled_count}/{len(KINK_CATEGORIES)} enabled{current_task_info}
"""
        await update.message.reply_text(text)
    finally:
        db.close()


async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏠 Home", callback_data="loc_home")],
        [InlineKeyboardButton("💼 Work", callback_data="loc_work")],
        [InlineKeyboardButton("🌆 Public", callback_data="loc_public")],
    ]
    await update.message.reply_text("📍 Where?", reply_markup=InlineKeyboardMarkup(keyboard))


async def location_detail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        if not context.args:
            current = user.location_detail or "Not set"
            await update.message.reply_text(f"Current: {current}\n\n/locationdetail bedroom")
            return
        
        detail = " ".join(context.args)
        user.location_detail = detail
        db.commit()
        await update.message.reply_text(f"📍 Set: {detail}")
    finally:
        db.close()


async def kinks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show and toggle kink preferences"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        if not context.args:
            await display_kinks_menu(update, context, user)
            return
        
        # Toggle specific kink by name
        kink_name = " ".join(context.args).lower()
        matched = None
        
        for kink_id, kink_data in KINK_CATEGORIES.items():
            if kink_name in kink_id or kink_name in kink_data['name'].lower():
                matched = kink_id
                break
        
        if matched:
            current = getattr(user.parameters, KINK_CATEGORIES[matched]['db_field'], True)
            setattr(user.parameters, KINK_CATEGORIES[matched]['db_field'], not current)
            db.commit()
            
            status = "ON ✅" if not current else "OFF ❌"
            await update.message.reply_text(
                f"*{KINK_CATEGORIES[matched]['name']}*: {status}\n\n"
                f"{get_kink_status_text(user)}",
                parse_mode='Markdown'
            )
        else:
            available = "\n".join([f"• {k['name']}" for k in KINK_CATEGORIES.values()])
            await update.message.reply_text(f"Kink not found. Available:\n{available}")
            
    finally:
        db.close()


async def nightmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        params = user.parameters
        
        if not context.args:
            status = "ON" if params.night_mode_enabled else "OFF"
            await update.message.reply_text(f"Night: {status} ({params.night_mode_start}:00-{params.night_mode_end}:00)")
            return
        
        action = context.args[0].lower()
        
        if action == "on":
            params.night_mode_enabled = True
            db.commit()
            await update.message.reply_text("🌙 ON")
        elif action == "off":
            params.night_mode_enabled = False
            db.commit()
            await update.message.reply_text("☀️ OFF")
        elif action == "setstart" and len(context.args) > 1:
            params.night_mode_start = int(context.args[1])
            db.commit()
            await update.message.reply_text(f"Start: {params.night_mode_start}:00")
        elif action == "setend" and len(context.args) > 1:
            params.night_mode_end = int(context.args[1])
            db.commit()
            await update.message.reply_text(f"End: {params.night_mode_end}:00")
    finally:
        db.close()


async def selfie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        race = getattr(user.parameters, 'avatar_race', 'white')
        hair = getattr(user.parameters, 'avatar_hair_color', 'black')
        await update.message.reply_text(f"Generating {race} {user.parameters.avatar_build}...")
        
        mood = AvatarMood.PLEASED if user.current_streak >= 3 else AvatarMood.COMMANDING
        image_data = AvatarGenerator.generate_avatar(user, mood, db)
        
        if image_data:
            await update.message.reply_photo(photo=InputFile(io.BytesIO(image_data), filename="dom.jpg"), caption="Here I am, pet.")
        else:
            await update.message.reply_text("Failed.")
    finally:
        db.close()


async def avatar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("White", callback_data="avatar_race_white")],
        [InlineKeyboardButton("Black", callback_data="avatar_race_black")],
        [InlineKeyboardButton("Asian", callback_data="avatar_race_asian")],
        [InlineKeyboardButton("Hispanic", callback_data="avatar_race_hispanic")],
        [InlineKeyboardButton("Mixed", callback_data="avatar_race_mixed")],
    ]
    await update.message.reply_text("Choose ethnicity:", reply_markup=InlineKeyboardMarkup(keyboard))


async def setfrequency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        params = user.parameters
        
        if len(context.args) < 2:
            await update.message.reply_text(
                f"Current: Every {params.min_interval_minutes}-{params.max_interval_minutes} min\n"
                f"Timeout: {params.task_timeout_minutes} min\n\n"
                f"Usage: /setfrequency 30 60"
            )
            return
        
        min_min = int(context.args[0])
        max_min = int(context.args[1])
        
        if min_min == 0 and max_min == 0:
            params.min_interval_minutes = 99999
            params.max_interval_minutes = 99999
            db.commit()
            await update.message.reply_text("⏸️ Scheduled messages disabled.")
            return
        
        if min_min >= max_min:
            await update.message.reply_text("❌ Min must be less than max")
            return
        
        if min_min < 5:
            await update.message.reply_text("❌ Minimum is 5 minutes")
            return
        
        params.min_interval_minutes = min_min
        params.max_interval_minutes = max_min
        db.commit()
        
        schedule_next_message()
        await update.message.reply_text(f"✅ Set: Every {min_min}-{max_min} minutes")
        
    except ValueError:
        await update.message.reply_text("❌ Use numbers: /setfrequency 60 180")
    finally:
        db.close()


async def setcreativity_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        if not context.args:
            await update.message.reply_text(f"Current creativity: {user.parameters.task_creativity_level:.1f}/1.0")
            return
        
        level = float(context.args[0])
        level = max(0.0, min(1.0, level))
        
        user.parameters.task_creativity_level = level
        db.commit()
        await update.message.reply_text(f"✅ Creativity: {level:.1f}")
        
    except ValueError:
        await update.message.reply_text("❌ Use 0-1")
    finally:
        db.close()


async def setrisk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        if not context.args:
            await update.message.reply_text(f"Current risk: {user.parameters.risk_tolerance:.1f}/1.0")
            return
        
        level = float(context.args[0])
        level = max(0.0, min(1.0, level))
        
        user.parameters.risk_tolerance = level
        db.commit()
        await update.message.reply_text(f"✅ Risk: {level:.1f}")
        
    except ValueError:
        await update.message.reply_text("❌ Use 0-1")
    finally:
        db.close()


async def release_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        if not user.current_task_id:
            await update.message.reply_text("No active task.")
            return
        
        task = db.query(Task).filter(Task.id == user.current_task_id).first()
        if task:
            task.status = TaskStatus.RELEASED.value
            user.failed_tasks += 1
            user.reward_points = max(0, user.reward_points - 20)
            user.current_task_id = None
            user.awaiting_response = False
            db.commit()
            await update.message.reply_text("⚠️ Released. -20 points.")
    finally:
        db.close()


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Testing Venice AI...")
    
    if not VENICE_API_KEY:
        await update.message.reply_text("❌ VENICE_API_KEY not set!")
        return
    
    try:
        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": [{"role": "user", "content": "Say 'Venice AI is working!'"}],
                "max_tokens": 100
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            await update.message.reply_text(f"✅ {content}")
        else:
            await update.message.reply_text(f"❌ Error {response.status_code}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, is_command=False)


# ============================================================================
# SCHEDULING
# ============================================================================

def schedule_next_message():
    try:
        scheduler.remove_all_jobs()
    except:
        pass
    
    db = SessionLocal()
    try:
        user = get_or_create_user(db, USER_CHAT_ID)
        params = user.parameters
        
        if params.min_interval_minutes >= 99999:
            logger.info("Scheduled messages disabled")
            return
        
        if params.night_mode_enabled:
            current_hour = (datetime.utcnow() - timedelta(hours=7)).hour
            is_night = current_hour >= params.night_mode_start or current_hour < params.night_mode_end
        else:
            is_night = False
            
        minutes = random.randint(params.min_interval_minutes, params.max_interval_minutes)
        night_mode_end = params.night_mode_end
        
    finally:
        db.close()
    
    if is_night:
        next_time = datetime.utcnow().replace(hour=(night_mode_end + 7) % 24, minute=0)
        if current_hour >= night_mode_end:
            next_time += timedelta(days=1)
        
        scheduler.add_job(send_scheduled_message, trigger="date", run_date=next_time, id="dom_message")
        logger.info(f"Scheduled for after night mode: {next_time}")
    else:
        scheduler.add_job(send_scheduled_message, trigger=IntervalTrigger(minutes=minutes), id="dom_message")
        logger.info(f"Scheduled next message in {minutes} minutes")


async def send_scheduled_message():
    db = SessionLocal()
    try:
        user = get_or_create_user(db, USER_CHAT_ID)
        params = user.parameters
        
        if user.current_task_id:
            task = db.query(Task).filter(Task.id == user.current_task_id).first()
            if task and task.status == TaskStatus.PENDING.value:
                time_left = task.deadline - datetime.utcnow()
                minutes_left = int(time_left.total_seconds() / 60)
                logger.info(f"User has active task ({minutes_left}m left), skipping")
                schedule_next_message()
                return
        
        if params.min_interval_minutes >= 99999:
            return
        
        if params.night_mode_enabled:
            current_hour = (datetime.utcnow() - timedelta(hours=7)).hour
            if current_hour >= params.night_mode_start or current_hour < params.night_mode_end:
                return
        
        await expire_old_tasks(user, db)
        task_data = await get_smart_task_for_user(user, db)
        
        deadline = datetime.utcnow() + timedelta(minutes=params.task_timeout_minutes)
        task = Task(
            user_id=user.id,
            description=task_data["description"],
            task_type=task_data["task_type"],
            requires_photo=True,
            intensity=task_data["difficulty"],
            deadline=deadline,
            ai_generated=task_data.get("ai_generated", False),
            task_category=task_data.get("task_category", "general"),
            risk_level=task_data.get("risk_level", "medium"),
            creativity_score=task_data.get("creativity_score", 0.5),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        db.commit()
        
        task_id = task.id
        task_description = task_data["description"]
        task_ai_generated = task_data.get("ai_generated", False)
        timeout_minutes = params.task_timeout_minutes
        
        image_data = AvatarGenerator.generate_avatar(user, AvatarMood.COMMANDING, db)
        
    finally:
        db.close()
    
    if not application or not application.bot:
        logger.error("Application not initialized")
        return
    
    keyboard = [
        [InlineKeyboardButton("✓ Complete", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton("✗ Fail", callback_data=f"fail_{task_id}")],
    ]
    
    ai_badge = "🤖 " if task_ai_generated else ""
    description = truncate_for_telegram(task_description, 600)
    full_message = truncate_for_telegram(
        f"{ai_badge}📋 TASK:\n{description}\n\n⏰ You have 30 minutes to complete.\n\n📸 SELFIE REQUIRED",
        950
    )
    
    sent = False
    for attempt in range(3):
        try:
            if image_data:
                await application.bot.send_photo(
                    chat_id=USER_CHAT_ID,
                    photo=InputFile(io.BytesIO(image_data), filename="task.jpg"),
                    caption=full_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    read_timeout=60,
                    write_timeout=60,
                )
            else:
                await application.bot.send_message(
                    chat_id=USER_CHAT_ID,
                    text=full_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            sent = True
            break
        except Exception as e:
            logger.warning(f"Send attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
    
    if not sent:
        logger.error("Failed to send scheduled message")
    
    schedule_next_message()


# ============================================================================
# ERROR HANDLER
# ============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Exception: {context.error}", exc_info=True)


# ============================================================================
# MAIN
# ============================================================================

def main():
    global application
    
    logger.info("Starting Dom Bot v6.0 - Kink Customization Edition")
    time.sleep(5)
    
    try:
        scheduler.start()
        logger.info("AsyncIO Scheduler started")
    except Exception as e:
        logger.warning(f"Scheduler issue: {e}")
    
    schedule_next_message()
    
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(60)
        .pool_timeout(120)
        .build()
    )
    
    application.add_error_handler(error_handler)
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("location", location_command))
    application.add_handler(CommandHandler("locationdetail", location_detail_command))
    application.add_handler(CommandHandler("kinks", kinks_command))
    application.add_handler(CommandHandler("nightmode", nightmode_command))
    application.add_handler(CommandHandler("selfie", selfie_command))
    application.add_handler(CommandHandler("avatar", avatar_command))
    application.add_handler(CommandHandler("setfrequency", setfrequency_command))
    application.add_handler(CommandHandler("setcreativity", setcreativity_command))
    application.add_handler(CommandHandler("setrisk", setrisk_command))
    application.add_handler(CommandHandler("release", release_command))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.PHOTO, enhanced_photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("Dom Bot v6.0 - Running with kink customization")
    
    application.run_polling(
        poll_interval=1.0,
        timeout=30,
        drop_pending_updates=True,
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60,
        pool_timeout=120,
    )


if __name__ == "__main__":
    main()