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
    
    # Existing params
    learning_enabled = Column(Boolean, default=True)
    analysis_frequency = Column(Integer, default=5)
    adaptation_rate = Column(Float, default=0.3)
    possessiveness = Column(Float, default=0.6)
    degradation_level = Column(Float, default=0.4)
    psychological_focus = Column(Float, default=0.5)
    unpredictability = Column(Float, default=0.5)
    photo_demand_frequency = Column(Float, default=0.95)
    task_timeout_minutes = Column(Integer, default=15)
    escalation_threshold = Column(Integer, default=2)
    verbosity = Column(String, default="medium")
    response_delay_enabled = Column(Boolean, default=True)
    min_response_delay_seconds = Column(Integer, default=2)
    max_response_delay_seconds = Column(Integer, default=10)
    min_interval_minutes = Column(Integer, default=60)
    max_interval_minutes = Column(Integer, default=180)
    active_hours_start = Column(Integer, default=8)
    active_hours_end = Column(Integer, default=20)  # Changed to 8pm
    preferred_task_types = Column(JSON, default=list)
    avoided_topics = Column(JSON, default=list)
    avatar_enabled = Column(Boolean, default=True)
    avatar_frequency = Column(Float, default=0.7)
    
    # Enhanced avatar params
    avatar_style = Column(String, default="photorealistic")
    avatar_ethnicity = Column(String, default="mixed")
    avatar_nationality = Column(String, default="mediterranean")  # NEW
    avatar_build = Column(String, default="muscular")
    avatar_hair = Column(String, default="dark")
    avatar_hair_length = Column(String, default="short")  # NEW
    avatar_hair_color = Column(String, default="black")  # NEW
    avatar_age_appearance = Column(String, default="28")
    
    # Task system params
    rewards_enabled = Column(Boolean, default=True)
    reward_frequency = Column(Float, default=0.1)
    check_in_frequency = Column(Integer, default=3)
    max_check_ins = Column(Integer, default=5)
    public_task_ratio = Column(Float, default=0.7)
    progressive_photo_count = Column(Integer, default=3)
    conversation_ratio = Column(Float, default=0.4)  # NEW: 40% conversation
    surprise_task_chance = Column(Float, default=0.15)  # NEW
    stale_location_hours = Column(Integer, default=4)  # NEW
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
    
    # NEW: Location tracking
    current_location = Column(String, default=LocationType.UNKNOWN.value)
    last_location_update = Column(DateTime, nullable=True)


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
    is_extended_hold = Column(Boolean, default=False)  # NEW
    location_type = Column(String, default=LocationType.UNKNOWN.value)  # NEW
    difficulty = Column(String, default=IntensityLevel.HIGH.value)  # NEW


class TaskCheckIn(Base):  # NEW TABLE
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


# ============================================================================
# ENHANCED AVATAR GENERATOR
# ============================================================================

class AvatarGenerator:
    MOOD_PROMPTS = {
        AvatarMood.COMMANDING: {
            "description": "standing tall, arms crossed, intense eye contact, powerful stance, full body visible head to toe",
            "clothing": "tight black briefs or jockstrap, harness",
            "expression": "intense, commanding, expectant",
            "setting": "minimalist dark room, dramatic lighting",
        },
        AvatarMood.PLEASED: {
            "description": "slight confident smile, relaxed posture, approving look, complete figure visible",
            "clothing": "unbuttoned shirt or briefs showing physique",
            "expression": "satisfied, proud, approving",
            "setting": "bedroom or private gym",
        },
        AvatarMood.DISAPPOINTED: {
            "description": "crossed arms, head tilted, looking down, full body composition",
            "clothing": "formal wear or leather",
            "expression": "disappointed, stern, judgmental",
            "setting": "office or dungeon",
        },
        AvatarMood.ANGRY: {
            "description": "fists clenched, leaning forward, aggressive, entire body in frame",
            "clothing": "sweat-soaked tank or bare chest",
            "expression": "angry, furious, dangerous",
            "setting": "gym, harsh lighting",
        },
        AvatarMood.THOUGHTFUL: {
            "description": "sitting, contemplative, calculating, full figure visible",
            "clothing": "casual, sweatpants low, bare torso",
            "expression": "thoughtful, scheming",
            "setting": "private study",
        },
        AvatarMood.SEDUCTIVE: {
            "description": "reclining, inviting but dominant, complete body visible",
            "clothing": "minimal - briefs or towel",
            "expression": "seductive, tempting, knowing smirk",
            "setting": "luxury bedroom",
        },
        AvatarMood.DOMINANT: {
            "description": "standing over, power pose, ownership, head to toe visible",
            "clothing": "leather harness, chaps, boots",
            "expression": "possessive, dominant",
            "setting": "dungeon or throne",
        },
        AvatarMood.WORKOUT: {
            "description": "sweaty post-workout, muscles pumped, glistening, full body",
            "clothing": "tight compression shorts",
            "expression": "intense, focused, powerful",
            "setting": "gym or locker room",
        },
        AvatarMood.DEMANDING: {
            "description": "close-up, intense stare, finger pointing at camera, demanding obedience, full figure",
            "clothing": "unzipped pants, bare chest, leather accessories",
            "expression": "demanding, impatient, expectant",
            "setting": "dimly lit room, shadows across face",
        },
        AvatarMood.SUSPICIOUS: {
            "description": "squinting, head tilted, examining something closely, complete body",
            "clothing": "open shirt, revealing physique",
            "expression": "suspicious, scrutinizing, doubtful",
            "setting": "office with harsh overhead lighting",
        },
        AvatarMood.EXHIBITIONIST: {
            "description": "outdoors or public space, confident pose, exposed skin, full body visible",
            "clothing": "minimal - thong, harness, or barely covered",
            "expression": "bold, daring, challenging",
            "setting": "alleyway, public bathroom, or risky outdoor location",
        },
        AvatarMood.CRUEL: {
            "description": "towering angle, mocking smirk, dismissive gesture, entire figure",
            "clothing": "full leather, boots, gloves",
            "expression": "cruel, mocking, sadistic grin",
            "setting": "dungeon, chains visible, dark atmosphere",
        },
        AvatarMood.INSPECTING: {
            "description": "holding phone or photo, examining intently, full body composition",
            "clothing": "casual, robe partially open",
            "expression": "critical, evaluating, judging",
            "setting": "private quarters, intimate lighting",
        },
        AvatarMood.FLIRTY: {
            "description": "playful pose, winking or smirking, relaxed stance, complete figure",
            "clothing": "casual, shirt unbuttoned, jeans low",
            "expression": "flirty, playful, teasing",
            "setting": "cozy bedroom or living room",
        },
        AvatarMood.MOCKING: {
            "description": "laughing or smirking dismissively, confident posture, full body",
            "clothing": "dominant attire, leather or minimal",
            "expression": "mocking, amused, superior",
            "setting": "throne or dominant position",
        },
        AvatarMood.CURIOUS: {
            "description": "leaning forward, interested expression, head tilted, full visible",
            "clothing": "casual, approachable but dominant",
            "expression": "curious, intrigued, questioning",
            "setting": "intimate setting, soft lighting",
        },
    }

    @staticmethod
    def build_prompt(user: UserState, mood: AvatarMood) -> str:
        params = user.parameters
        mood_data = AvatarGenerator.MOOD_PROMPTS.get(
            mood, AvatarGenerator.MOOD_PROMPTS[AvatarMood.COMMANDING]
        )
        
        # Build physical description based on build type
        if params.avatar_build == "twink":
            physical = f"{params.avatar_age_appearance}-year-old {params.avatar_ethnicity} {params.avatar_nationality} twink, extremely slender and smooth physique, lithe and youthful, {params.avatar_hair_length} {params.avatar_hair_color} hair"
        elif params.avatar_build == "muscular":
            physical = f"{params.avatar_age_appearance}-year-old {params.avatar_ethnicity} {params.avatar_nationality} man, muscular and defined physique, powerful build, {params.avatar_hair_length} {params.avatar_hair_color} hair"
        elif params.avatar_build == "lean":
            physical = f"{params.avatar_age_appearance}-year-old {params.avatar_ethnicity} {params.avatar_nationality} man, lean and toned physique, athletic build, {params.avatar_hair_length} {params.avatar_hair_color} hair"
        else:
            physical = f"{params.avatar_age_appearance}-year-old {params.avatar_ethnicity} {params.avatar_nationality} man, {params.avatar_build} physique, {params.avatar_hair_length} {params.avatar_hair_color} hair"
        
        # Enhanced prompt with framing fixes
        prompt = f"{params.avatar_style} photograph of a dominant {physical}, {mood_data['description']}, {mood_data['clothing']}, {mood_data['expression']}, {mood_data['setting']}, highly detailed, professional lighting, masculine, powerful, 4k quality, full body visible from head to toe, complete figure in frame, proper proportions"
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
            
            # Use 768x512 for better full body framing (was 512x768)
            response = requests.post(
                VENICE_IMAGE_URL,
                headers={
                    "Authorization": f"Bearer {VENICE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "chroma",
                    "prompt": prompt,
                    "width": 768,
                    "height": 512,
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
        elif context == "checkin":
            return AvatarMood.DEMANDING
        elif context == "inspecting":
            return AvatarMood.INSPECTING
        elif context == "conversation":
            # Random conversation mood
            return random.choice([
                AvatarMood.THOUGHTFUL, 
                AvatarMood.FLIRTY, 
                AvatarMood.CURIOUS,
                AvatarMood.MOCKING
            ])
        elif user.intensity == IntensityLevel.EXTREME.value:
            return AvatarMood.DOMINANT
        else:
            return random.choice([AvatarMood.COMMANDING, AvatarMood.THOUGHTFUL])


# ============================================================================
# EXTREME TASK TEMPLATES
# ============================================================================

EXTREME_TASK_TEMPLATES = {
    LocationType.WORK: [
        "Go to your office bathroom. Strip completely naked. Take a photo showing your work ID badge visible. You have {timeout} minutes.",
        "At your desk, hand down your pants, take a photo showing your computer screen with work visible. Quick.",
        "Find an empty conference room. Strip naked. Photo showing the conference table. {timeout} minutes.",
        "Go to the work parking garage. Find a corner. Drop pants to ankles. Photo from behind showing cars. {timeout} minutes.",
        "In your cubicle, pants unzipped, hand inside, photo showing cubicle walls. Risky. {timeout} minutes.",
        "Office kitchen: bend over with pants down, photo showing the coffee machine. Quick before someone comes.",
        "Stairwell at work: every floor, remove one item of clothing. Photo at bottom floor naked.",
        "Work bathroom mirror: write 'OWNED' on chest, photo with work logo visible in reflection.",
        "Under your desk: pull pants down, photo showing view from under desk looking out.",
        "Elevator at work: stop between floors, strip, photo showing elevator buttons and emergency panel.",
    ],
    LocationType.HOME: [
        "Strip naked. Kneel facing a wall. Do not move until I release you. Photo proof of position. Check-ins will follow.",
        "Edge yourself to the brink. Stop. Hold the position. Photo of your state. Do not finish until I say.",
        "Naked, on all fours, forehead to floor. Photo proof. Stay. I will check on you.",
        "Stand in the corner, naked, nose touching wall. Photo showing your back. Hold position until released.",
        "Naked, hands behind back, kneeling on hard floor. Photo proof. Suffer for me.",
        "In front of a window facing the street: naked, photo showing window view. Risky.",
        "On your balcony or porch: completely naked, photo showing house number or mailbox.",
        "Living room: naked, legs spread, photo showing front door in background.",
        "Kitchen: naked, bent over counter, photo showing stove/oven visible.",
        "Bedroom: tied or holding position, photo showing clock/time for duration proof.",
    ],
    LocationType.PUBLIC: [
        "Mall fitting room: strip naked, photo showing clothes on hanger and your naked reflection.",
        "Public library bathroom: naked, photo showing books or library sign visible.",
        "Coffee shop bathroom: strip, photo showing coffee cup or shop logo.",
        "Gym locker room: naked, photo showing locker number and your reflection.",
        "Movie theater bathroom: naked, photo showing movie poster visible.",
        "Restaurant bathroom: strip, photo showing menu or receipt visible.",
        "Bar/club bathroom: naked, photo showing graffiti or mirror message.",
        "Hotel hallway: naked, quick photo showing room numbers.",
        "Parking garage: naked, photo showing level sign and parked cars.",
        "Park restroom: naked, photo showing park map or sign visible.",
    ],
    LocationType.TRANSIT: [
        "Your car: pull over, strip naked, photo showing steering wheel and road visible through window.",
        "Public bus: back seat, hand down pants, photo showing bus window and seats.",
        "Train/subway: bathroom or corner, pants down, photo showing train interior.",
        "Uber/taxi: back seat, exposed, photo showing driver's seat or dashboard.",
        "Highway rest stop: bathroom, naked, photo showing highway sign or map.",
        "Airport bathroom: strip, photo showing gate number or terminal sign.",
        "Parking lot: in your car, naked, photo showing store signs visible.",
        "Gas station: bathroom, naked, photo showing gas pump visible through window.",
    ],
    LocationType.SOCIAL: [
        "Friend's house bathroom: naked, photo showing their towels or decor.",
        "Party bathroom: strip, photo showing party decorations visible.",
        "Family gathering: bathroom, risky exposure, photo showing family photos in background.",
        "Date's place: bathroom, naked, photo showing their personal items.",
        "Public event: portable toilet, strip, photo showing event flyer or ticket.",
    ],
}

# Check-in messages
CHECK_IN_MESSAGES = {
    "demand_status": [
        "Still waiting. Send me a photo proving you haven't moved.",
        "Check-in. Photo. Now. Prove you're still obeying.",
        "I want to see you still in position. Photo proof required.",
        "Time check. Where's my proof you're still being good?",
        "Don't move. But send me a photo showing me you haven't.",
    ],
    "escalate_position": [
        "Good. Now spread your legs wider. Photo proof.",
        "Stay there. But now I want you to add: hands behind back. Photo.",
        "Hold position. Additionally: I want to see your face showing your suffering. Photo.",
        "You're doing well. Make it harder: arch your back more. Photo proof.",
        "Maintain position. New requirement: I want to hear you beg in the next photo's caption.",
    ],
    "mock_suffering": [
        "Are your knees hurting? Good. Send proof you're still there.",
        "How long has it been? Doesn't matter. You'll wait longer. Photo.",
        "I bet you want to move. Don't. Photo proof of obedience.",
        "Your suffering pleases me. Show me more. Photo.",
        "Still there? I'm impressed. Now suffer more for me. Photo.",
    ],
    "release_commands": [
        "You've suffered enough. You may move. Send one final photo of your state.",
        "Released. But first: photo proof of what I did to you.",
        "You may stop. After you send me a photo showing the result.",
        "Task complete. One last photo required for my satisfaction.",
        "You're free. But I want to see the evidence of your obedience first. Photo.",
    ],
}

# Conversation starters (non-task)
CONVERSATION_PROMPTS = [
    "How is my pet feeling today? Tell me honestly.",
    "What have you been thinking about since we last spoke?",
    "I want to know what you're wearing right now. Describe it.",
    "Tell me about your day. I want details.",
    "Are you alone right now? Be honest.",
    "What's something you've been too shy to tell me?",
    "How do you feel when you obey me? Describe it.",
    "Tell me about a time you felt truly owned.",
    "What are you doing right now, exact position?",
    "I want to know your thoughts. Speak freely, pet.",
]


# ============================================================================
# REWARD SYSTEM
# ============================================================================

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


# ============================================================================
# LEARNING ENGINE
# ============================================================================

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


# ============================================================================
# AI RESPONSE GENERATION
# ============================================================================

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


def generate_conversation_response(user: UserState, db: Session) -> str:
    """Generate a non-task conversation response"""
    prompt = random.choice(CONVERSATION_PROMPTS)
    return generate_ai_response(user, prompt, db)


# ============================================================================
# TASK GENERATION
# ============================================================================

def check_understanding_mode(user_message: str) -> bool:
    """Check if user is indicating they can't complete a task"""
    refusal_indicators = [
        "can't", "cannot", "impossible", "too risky", "too dangerous",
        "won't do", "refuse", "scared", "afraid", "not safe",
        "can't do this", "too much", "too extreme", "no way"
    ]
    msg_lower = user_message.lower()
    return any(indicator in msg_lower for indicator in refusal_indicators)


def generate_task_for_location(user: UserState, location: LocationType, db: Session) -> dict:
    """Generate location-appropriate task"""
    templates = EXTREME_TASK_TEMPLATES.get(location, EXTREME_TASK_TEMPLATES[LocationType.PUBLIC])
    
    # Filter by intensity
    if user.intensity == IntensityLevel.EXTREME.value:
        # Use all templates
        pass
    elif user.intensity == IntensityLevel.HIGH.value:
        # Skip most extreme (first few of each category are most extreme)
        templates = templates[3:] if len(templates) > 3 else templates
    elif user.intensity == IntensityLevel.MEDIUM.value:
        # Use milder half
        templates = templates[len(templates)//2:]
    else:
        # Low intensity - use last few (mildest)
        templates = templates[-3:] if len(templates) > 3 else templates
    
    template = random.choice(templates)
    timeout = user.parameters.task_timeout_minutes
    
    description = template.format(timeout=timeout)
    
    # Determine if extended hold
    is_extended_hold = "until I release" in description.lower() or "do not move" in description.lower()
    
    return {
        "description": description,
        "task_type": location.value,
        "requires_photo": True,
        "is_extended_hold": is_extended_hold,
        "location_type": location.value,
        "difficulty": user.intensity,
    }


def offer_alternative_task(user: UserState, original_task: Task, db: Session) -> dict:
    """Offer milder alternative with punishment"""
    # Reduce intensity for alternative
    alternatives = [
        "Strip to underwear only (not naked) and take photo in mirror.",
        "Edge once but do not finish. Photo of your face showing frustration.",
        "Write 'I obey' on your chest 5 times. Photo proof.",
        "Kneel for 5 minutes (not until released). Photo of position.",
        "Go to bathroom, pull pants down to knees only. Quick photo.",
    ]
    
    description = random.choice(alternatives)
    
    return {
        "description": f"ALTERNATIVE TASK (with punishment):\n\n{description}\n\nPUNISHMENT: -15 points, intensity increased.\n\nThis is your mercy. Accept it.",
        "task_type": "alternative",
        "requires_photo": True,
        "is_extended_hold": False,
        "location_type": original_task.location_type,
        "difficulty": IntensityLevel.HIGH.value,
        "is_alternative": True,
    }


# ============================================================================
# SCHEDULING & CHECK-INS
# ============================================================================

async def schedule_task_checkins(user: UserState, task: Task, db: Session):
    """Schedule periodic check-ins for extended hold tasks"""
    params = user.parameters
    max_check_ins = params.max_check_ins
    interval = params.check_in_frequency
    
    for i in range(1, max_check_ins + 1):
        check_in_time = datetime.utcnow() + timedelta(minutes=interval * i)
        
        if i == max_check_ins:
            message_type = "release"
            is_final = True
        elif i % 2 == 0:
            message_type = "escalate"
        else:
            message_type = "demand"
        
        scheduler.add_job(
            lambda u=user, t=task, mt=message_type, num=i: asyncio.run(
                send_checkin_message(u, t, mt, num)
            ),
            trigger="date",
            run_date=check_in_time,
            id=f"checkin_{user.chat_id}_{task.id}_{i}",
            replace_existing=True,
        )


async def send_checkin_message(user: UserState, task: Task, message_type: str, check_in_num: int):
    """Send check-in message during extended tasks"""
    db = SessionLocal()
    try:
        current_task = db.query(Task).filter(Task.id == task.id).first()
        if not current_task or current_task.status not in [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]:
            return
        
        if message_type == "release":
            messages = CHECK_IN_MESSAGES["release_commands"]
            mood = AvatarMood.PLEASED if user.consecutive_failures == 0 else AvatarMood.COMMANDING
            current_task.status = TaskStatus.IN_PROGRESS.value
            db.commit()
        elif message_type == "escalate":
            messages = CHECK_IN_MESSAGES["escalate_position"]
            mood = AvatarMood.DEMANDING
        else:
            messages = CHECK_IN_MESSAGES["demand_status"]
            mood = AvatarMood.SUSPICIOUS
        
        message = random.choice(messages)
        image_data = AvatarGenerator.generate_avatar(user, mood, db)
        
        if message_type == "release":
            keyboard = [[InlineKeyboardButton("📸 Final Photo", callback_data=f"finalphoto_{task.id}")]]
        else:
            keyboard = [
                [InlineKeyboardButton("📸 Send Proof", callback_data=f"checkinphoto_{task.id}_{check_in_num}")],
                [InlineKeyboardButton("❌ I Moved", callback_data=f"moved_{task.id}")],
            ]
        
        if image_data:
            await bot.send_photo(
                chat_id=user.chat_id,
                photo=InputFile(io.BytesIO(image_data), filename=f"checkin_{check_in_num}.jpg"),
                caption=f"⏰ CHECK-IN #{check_in_num}\n\n{message}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await bot.send_message(
                chat_id=user.chat_id,
                text=f"⏰ CHECK-IN #{check_in_num}\n\n{message}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        
        checkin = TaskCheckIn(
            task_id=task.id,
            check_in_number=check_in_num,
            message=message,
            requires_response=True,
            is_final=(message_type == "release"),
        )
        db.add(checkin)
        db.commit()
        
    except Exception as e:
        logger.error(f"Check-in error: {e}")
    finally:
        db.close()


async def check_escalation(db: Session, user: UserState):
    """Check if task has expired and escalate"""
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


# ============================================================================
# MESSAGE HANDLERS
# ============================================================================

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_command: bool = False):
    """Enhanced message processing with conversation mode and understanding"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        params = user.parameters
        
        # Night mode check (8pm-8am)
        current_hour = datetime.utcnow().hour
        if current_hour >= 20 or current_hour < 8:
            # Night mode - conversation only, no tasks
            if update.message.text:
                user_msg = ConversationMessage(user_id=user.id, message=update.message.text, is_from_dom=False)
                db.add(user_msg)
                db.commit()
                
                ai_response = generate_ai_response(user, update.message.text, db)
                await update.message.reply_text(f"🌙 Night Mode 🌙\n\n{ai_response}\n\n(Sleep well, pet. Tasks resume at 8am)")
            return
        
        # Safe word check
        if user.safe_word_active and user.safe_word_until and datetime.utcnow() < user.safe_word_until:
            if update.message.text and SAFE_WORD in update.message.text.upper():
                pass
            else:
                await update.message.reply_text("🛑 Safe word active.")
                return
        
        user_text = update.message.text if update.message.text else "[image]"
        
        # Check for understanding mode (user saying they can't do task)
        if user.current_task_id and check_understanding_mode(user_text):
            task = db.query(Task).filter(Task.id == user.current_task_id).first()
            if task and task.status == TaskStatus.PENDING.value:
                # Offer alternative
                alt_task = offer_alternative_task(user, task, db)
                
                # Mark original as failed
                task.status = TaskStatus.FAILED.value
                user.failed_tasks += 1
                user.consecutive_failures += 1
                user.reward_points = max(0, user.reward_points - 15)
                user.intensity = escalate_intensity(IntensityLevel(user.intensity)).value
                db.commit()
                
                # Send alternative
                image_data = AvatarGenerator.generate_avatar(user, AvatarMood.CRUEL, db)
                msg = alt_task["description"]
                
                keyboard = [
                    [InlineKeyboardButton("✓ Accept Alternative", callback_data=f"complete_alt_{task.id}")],
                    [InlineKeyboardButton("✗ Refuse", callback_data=f"fail_{task.id}")],
                ]
                
                if image_data:
                    await update.message.reply_photo(
                        photo=InputFile(io.BytesIO(image_data), filename="cruel.jpg"),
                        caption=f"😈 MERCY OFFERED 😈\n\n{msg}",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                else:
                    await update.message.reply_text(
                        f"😈 MERCY OFFERED 😈\n\n{msg}",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                return
        
        # Log message
        user_msg = ConversationMessage(user_id=user.id, message=user_text, is_from_dom=False)
        db.add(user_msg)
        user.interaction_count += 1
        if user.interaction_count % params.analysis_frequency == 0:
            LearningEngine.analyze_user(db, user)
        db.commit()
        
        # Check for stale location
        location_stale = False
        if user.last_location_update:
            hours_since = (datetime.utcnow() - user.last_location_update).total_seconds() / 3600
            if hours_since > params.stale_location_hours:
                location_stale = True
        
        if location_stale and not is_command:
            # Ask for location update
            keyboard = [
                [InlineKeyboardButton("🏠 Home", callback_data="loc_home")],
                [InlineKeyboardButton("💼 Work", callback_data="loc_work")],
                [InlineKeyboardButton("🌆 Public", callback_data="loc_public")],
                [InlineKeyboardButton("🚗 Transit", callback_data="loc_transit")],
                [InlineKeyboardButton("🎉 Social", callback_data="loc_social")],
            ]
            await update.message.reply_text(
                f"📍 I don't know where you are (last updated {int(hours_since)} hours ago).\n\n"
                f"Tell me before I give you your next task.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return
        
        # Determine: conversation or task?
        # 40% conversation, 60% task (configurable)
        is_conversation = random.random() < params.conversation_ratio
        
        if is_conversation and not is_command:
            # Conversation mode
            ai_response = generate_conversation_response(user, db)
            
            dom_msg = ConversationMessage(
                user_id=user.id,
                message=ai_response,
                is_from_dom=True,
                has_avatar=random.random() < params.avatar_frequency,
            )
            db.add(dom_msg)
            db.commit()
            
            if dom_msg.has_avatar:
                mood = AvatarGenerator.determine_mood(user, "conversation")
                image_data = AvatarGenerator.generate_avatar(user, mood, db)
                if image_data:
                    await update.message.reply_photo(
                        photo=InputFile(io.BytesIO(image_data), filename="dom_chat.jpg"),
                        caption=ai_response,
                    )
                else:
                    await update.message.reply_text(ai_response)
            else:
                await update.message.reply_text(ai_response)
            return
        
        # Task mode
        location = LocationType(user.current_location) if user.current_location else LocationType.UNKNOWN
        
        # Surprise task chance
        is_surprise = random.random() < params.surprise_task_chance
        
        task_data = generate_task_for_location(user, location, db)
        
        # Create task
        deadline = datetime.utcnow() + timedelta(minutes=params.task_timeout_minutes)
        if is_surprise:
            deadline = datetime.utcnow() + timedelta(minutes=5)  # 5 min for surprise
        
        task = Task(
            user_id=user.id,
            description=task_data["description"],
            task_type=task_data["task_type"],
            requires_photo=task_data["requires_photo"],
            intensity=task_data["difficulty"],
            deadline=deadline,
            is_extended_hold=task_data.get("is_extended_hold", False),
            location_type=task_data.get("location_type", location.value),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        user.total_tasks += 1
        user.awaiting_response = True
        user.current_task_id = task.id
        
        # Build keyboard
        keyboard = [
            [InlineKeyboardButton("✓ Task Complete", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("✗ I Failed", callback_data=f"fail_{task.id}")],
        ]
        
        # Determine mood
        if is_surprise:
            mood = AvatarMood.EXHIBITIONIST
            prefix = "🚨 SURPRISE TASK 🚨\n\n"
        elif task_data["location_type"] in ["work", "public"]:
            mood = AvatarMood.EXHIBITIONIST
            prefix = ""
        elif task_data.get("is_extended_hold"):
            mood = AvatarMood.DEMANDING
            prefix = ""
        else:
            mood = AvatarMood.COMMANDING
            prefix = ""
        
        image_data = AvatarGenerator.generate_avatar(user, mood, db)
        
        full_message = f"{prefix}📋 YOUR TASK:\n{task_data['description']}\n\n⏰ Deadline: {'5 minutes' if is_surprise else params.task_timeout_minutes + ' minutes'}\n\n📸 PHOTO PROOF REQUIRED"
        
        dom_msg = ConversationMessage(
            user_id=user.id,
            message=full_message,
            is_from_dom=True,
            has_avatar=True,
        )
        db.add(dom_msg)
        db.commit()
        
        if image_data:
            await update.message.reply_photo(
                photo=InputFile(io.BytesIO(image_data), filename="task.jpg"),
                caption=full_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await update.message.reply_text(
                full_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        
        # Schedule check-ins if extended hold
        if task_data.get("is_extended_hold"):
            await schedule_task_checkins(user, task, db)
        
        # Schedule escalation check
        scheduler.add_job(
            lambda: asyncio.run(check_escalation_wrapper(str(update.effective_chat.id))),
            trigger=IntervalTrigger(minutes=5 if is_surprise else params.task_timeout_minutes),
            id=f"escalation_check_{update.effective_chat.id}",
            replace_existing=True,
        )
                
    except Exception as e:
        logger.error(f"Process message error: {e}")
    finally:
        db.close()


async def enhanced_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced photo handler with multiple modes"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        photo_type = context.user_data.get("awaiting_photo_type", "task_completion")
        task_id = context.user_data.get("awaiting_photo_task_id")
        check_in_num = context.user_data.get("awaiting_checkin_num", 0)
        
        if not task_id:
            await process_message(update, context)
            return
        
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await update.message.reply_text("Task not found.")
            return
        
        if not update.message.photo:
            await update.message.reply_text("No photo detected. Try again.")
            return
        
        photo = update.message.photo[-1]
        file = await photo.get_file()
        task.photo_url = file.file_path
        
        if photo_type == "checkin":
            checkin = db.query(TaskCheckIn).filter(
                TaskCheckIn.task_id == task_id,
                TaskCheckIn.check_in_number == check_in_num
            ).first()
            if checkin:
                checkin.response_received = True
            
            mood = AvatarMood.INSPECTING
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            msg = random.choice([
                "I see you. Still there. Good.",
                "Proof received. You haven't moved. Satisfactory.",
                "I see you're obeying. Continue holding.",
                "Photo verified. Stay exactly as you are.",
            ])
            
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="inspecting.jpg"),
                    caption=f"✓ CHECK-IN #{check_in_num} VERIFIED\n\n{msg}",
                )
            else:
                await update.message.reply_text(f"✓ CHECK-IN #{check_in_num} VERIFIED\n\n{msg}")
            
            db.commit()
            
        elif photo_type == "final_release":
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            
            user.completed_tasks += 1
            user.current_streak += 1
            user.consecutive_failures = 0
            user.awaiting_response = False
            user.reward_points += 10
            
            context.user_data.pop("awaiting_photo_type", None)
            context.user_data.pop("awaiting_photo_task_id", None)
            context.user_data.pop("awaiting_checkin_num", None)
            
            mood = AvatarMood.PLEASED if user.current_streak >= 3 else AvatarMood.COMMANDING
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            msg = random.choice([
                "Released. You took that well. I'm pleased.",
                "You may move. Your obedience has been noted.",
                "Task complete. You suffered beautifully for me.",
                "You're free. For now. Your proof was satisfactory.",
            ])
            
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="released.jpg"),
                    caption=f"✓ TASK COMPLETE - RELEASED\n\n{msg}\n\n🔥 Streak: {user.current_streak} | ⭐ Points: +10",
                )
            else:
                await update.message.reply_text(f"✓ TASK COMPLETE\n\n{msg}")
            
            db.commit()
            
        else:
            # Standard completion
            task.status = TaskStatus.COMPLETED.value
            task.completed_at = datetime.utcnow()
            
            user.completed_tasks += 1
            user.current_streak += 1
            user.consecutive_failures = 0
            user.awaiting_response = False
            user.reward_points += 5
            
            context.user_data.pop("awaiting_photo_type", None)
            context.user_data.pop("awaiting_photo_task_id", None)
            
            mood = AvatarMood.INSPECTING if random.random() < 0.5 else AvatarMood.PLEASED
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            
            if user.current_streak >= 7:
                msg = "Excellent. Your proof pleases me. You've earned my attention."
            elif user.current_streak >= 3:
                msg = "Good pet. Proof received and approved."
            else:
                msg = "Satisfactory. Task complete."
            
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="approved.jpg"),
                    caption=f"✓ PROOF APPROVED\n\n{msg}\n\n🔥 Streak: {user.current_streak}",
                )
            else:
                await update.message.reply_text(f"✓ PROOF APPROVED\n\n{msg}")
            
            db.commit()
            
    except Exception as e:
        logger.error(f"Photo handler error: {e}")
        await update.message.reply_text("Error processing photo. Try again.")
    finally:
        db.close()


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced button callback"""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        data = query.data
        
        # Location updates
        if data.startswith("loc_"):
            location_map = {
                "loc_home": LocationType.HOME,
                "loc_work": LocationType.WORK,
                "loc_public": LocationType.PUBLIC,
                "loc_transit": LocationType.TRANSIT,
                "loc_social": LocationType.SOCIAL,
            }
            new_loc = location_map.get(data, LocationType.UNKNOWN)
            user.current_location = new_loc.value
            user.last_location_update = datetime.utcnow()
            db.commit()
            await query.edit_message_text(f"📍 Location updated: {new_loc.value}\n\nAwaiting my command...")
            return
        
        # Check-in photos
        if data.startswith("checkinphoto_"):
            parts = data.split("_")
            task_id = int(parts[1])
            check_in_num = int(parts[2])
            
            context.user_data["awaiting_photo_type"] = "checkin"
            context.user_data["awaiting_photo_task_id"] = task_id
            context.user_data["awaiting_checkin_num"] = check_in_num
            
            await query.edit_message_caption(
                caption=f"{query.message.caption}\n\n📸 Awaiting check-in #{check_in_num} photo..."
            )
            return
        
        # Final release photo
        if data.startswith("finalphoto_"):
            task_id = int(data.split("_")[1])
            
            context.user_data["awaiting_photo_type"] = "final_release"
            context.user_data["awaiting_photo_task_id"] = task_id
            
            await query.edit_message_caption(
                caption=f"{query.message.caption}\n\n📸 Send final proof of your state..."
            )
            return
        
        # "I Moved" confession
        if data.startswith("moved_"):
            task_id = int(data.split("_")[1])
            task = db.query(Task).filter(Task.id == task_id).first()
            
            if task:
                task.status = TaskStatus.FAILED.value
                user.failed_tasks += 1
                user.consecutive_failures += 1
                user.current_streak = 0
                user.awaiting_response = False
                user.intensity = escalate_intensity(IntensityLevel(user.intensity)).value
                db.commit()
                
                mood = AvatarMood.ANGRY if user.consecutive_failures > 1 else AvatarMood.DISAPPOINTED
                image_data = AvatarGenerator.generate_avatar(user, mood, db)
                msg = "You moved. You failed. Consequences incoming."
                
                if image_data:
                    await query.edit_message_caption(caption=f"❌ TASK FAILED\n\n{msg}")
                    await bot.send_photo(
                        chat_id=user.chat_id,
                        photo=InputFile(io.BytesIO(image_data), filename="disappointed.jpg"),
                        caption="I'm disappointed. You'll need to be punished.",
                    )
                else:
                    await query.edit_message_text(f"❌ TASK FAILED\n\n{msg}")
            return
        
        # Standard complete
        if data.startswith("complete_"):
            task_id = int(data.split("_")[1])
            task = db.query(Task).filter(Task.id == task_id).first()
            
            if task and task.status == TaskStatus.PENDING.value:
                if task.requires_photo:
                    context.user_data["awaiting_photo_type"] = "task_completion"
                    context.user_data["awaiting_photo_task_id"] = task_id
                    
                    await query.edit_message_caption(
                        caption=f"{query.message.caption}\n\n📸 Complete the task and send photo proof..."
                    )
                else:
                    task.status = TaskStatus.COMPLETED.value
                    task.completed_at = datetime.utcnow()
                    user.completed_tasks += 1
                    user.current_streak += 1
                    db.commit()
                    await query.edit_message_caption(caption="✓ Task completed!")
            return
        
        # Alternative task acceptance
        if data.startswith("complete_alt_"):
            task_id = int(data.split("_")[2])
            task = db.query(Task).filter(Task.id == task_id).first()
            
            if task:
                context.user_data["awaiting_photo_type"] = "task_completion"
                context.user_data["awaiting_photo_task_id"] = task_id
                
                await query.edit_message_caption(
                    caption=f"{query.message.caption}\n\n📸 Complete the alternative task and send photo proof..."
                )
            return
        
        # Fail
        if data.startswith("fail_"):
            task_id = int(data.split("_")[1])
            task = db.query(Task).filter(Task.id == task_id).first()
            
            if task and task.status == TaskStatus.PENDING.value:
                task.status = TaskStatus.FAILED.value
                user.failed_tasks += 1
                user.consecutive_failures += 1
                user.current_streak = 0
                user.awaiting_response = False
                user.intensity = escalate_intensity(IntensityLevel(user.intensity)).value
                db.commit()
                
                mood = AvatarMood.ANGRY if user.consecutive_failures > 2 else AvatarMood.DISAPPOINTED
                image_data = AvatarGenerator.generate_avatar(user, mood, db)
                msg = generate_ai_response(user, "My pet failed me. I am displeased.", db)
                
                if image_data:
                    await query.edit_message_caption(caption=f"❌ TASK FAILED\n\n{msg}")
                else:
                    await query.edit_message_text(f"❌ TASK FAILED\n\n{msg}")
            return
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
    finally:
        db.close()


# ============================================================================
# COMMANDS
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """Welcome, pet. I am your Dom.

I learn. I adapt. I reward. I punish.

Commands:
/status - Your standing
/location - Set your current location
/rewards - View your progress & milestones
/redeem - Spend points on rewards
/selfie - Request my image
/avatar - Customize my appearance
/analyze - Force learning analysis
/privileges - View earned perks
/release - Emergency release (with penalty)

Obey me, and you will be rewarded. Fail me, and face consequences."""
    await update.message.reply_text(welcome)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        compliance = (
            (user.completed_tasks / user.total_tasks * 100) if user.total_tasks > 0 else 0
        )
        location_str = user.current_location if user.current_location else "Unknown"
        
        text = f"""
📊 Your Status, pet

Intensity: {user.intensity.upper()}
Location: {location_str}
Tasks: {user.completed_tasks}/{user.total_tasks} ({compliance:.0f}%)
Current Streak: 🔥 {user.current_streak} tasks
Longest Streak: {user.longest_streak} tasks
Reward Points: ⭐ {user.reward_points}

Privileges: {', '.join(user.privileges) if user.privileges else 'None yet'}
"""
        await update.message.reply_text(text)
    finally:
        db.close()


async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set current location"""
    keyboard = [
        [InlineKeyboardButton("🏠 Home", callback_data="loc_home")],
        [InlineKeyboardButton("💼 Work", callback_data="loc_work")],
        [InlineKeyboardButton("🌆 Public", callback_data="loc_public")],
        [InlineKeyboardButton("🚗 Transit", callback_data="loc_transit")],
        [InlineKeyboardButton("🎉 Social", callback_data="loc_social")],
    ]
    await update.message.reply_text(
        "📍 Where are you right now, pet?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def rewards_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


async def selfie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


async def avatar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced avatar customization"""
    keyboard = [
        [
            InlineKeyboardButton("Muscular", callback_data="avatar_build_muscular"),
            InlineKeyboardButton("Lean", callback_data="avatar_build_lean"),
            InlineKeyboardButton("Twink", callback_data="avatar_build_twink"),
        ],
        [
            InlineKeyboardButton("Short Hair", callback_data="avatar_hair_short"),
            InlineKeyboardButton("Medium Hair", callback_data="avatar_hair_medium"),
            InlineKeyboardButton("Long Hair", callback_data="avatar_hair_long"),
        ],
        [
            InlineKeyboardButton("Black Hair", callback_data="avatar_color_black"),
            InlineKeyboardButton("Blonde", callback_data="avatar_color_blonde"),
            InlineKeyboardButton("Brunette", callback_data="avatar_color_brown"),
        ],
        [InlineKeyboardButton("Toggle Avatar", callback_data="avatar_toggle")],
    ]
    
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        params = user.parameters
        
        current = f"""
Current Appearance:
• Build: {params.avatar_build}
• Hair Length: {params.avatar_hair_length}
• Hair Color: {params.avatar_hair_color}
• Ethnicity: {params.avatar_ethnicity}
• Nationality: {params.avatar_nationality}
• Age: {params.avatar_age_appearance}
"""
        await update.message.reply_text(
            f"Customize how I appear to you, pet:\n{current}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    finally:
        db.close()


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


async def privileges_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
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
    finally:
        db.close()


async def release_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Emergency release from current task"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, str(update.effective_chat.id))
        
        if not user.current_task_id:
            await update.message.reply_text("You're not currently assigned a task.")
            return
        
        task = db.query(Task).filter(Task.id == user.current_task_id).first()
        if task and task.status in [TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]:
            task.status = TaskStatus.RELEASED.value
            task.completed_at = datetime.utcnow()
            
            user.failed_tasks += 1
            user.consecutive_failures += 1
            user.current_streak = 0
            user.awaiting_response = False
            user.reward_points = max(0, user.reward_points - 20)
            
            db.commit()
            
            mood = AvatarMood.DISAPPOINTED
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            msg = "You begged for release. Weak. Points deducted. You'll make this up to me."
            
            if image_data:
                await update.message.reply_photo(
                    photo=InputFile(io.BytesIO(image_data), filename="disappointed.jpg"),
                    caption=f"⚠️ EMERGENCY RELEASE\\n\\n{msg}\\n\\n⭐ Points: -20",
                )
            else:
                await update.message.reply_text(f"⚠️ EMERGENCY RELEASE\\n\\n{msg}")
        else:
            await update.message.reply_text("No active task to release you from.")
    finally:
        db.close()


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_message(update, context, is_command=False)


def schedule_next_message():
    """Schedule next random message"""
    try:
        scheduler.remove_all_jobs()
    except:
        pass
    
    db = next(get_db())
    user = get_or_create_user(db, USER_CHAT_ID)
    params = user.parameters
    
    # Check night mode
    from datetime import timedelta
    current_hour = (datetime.utcnow() - timedelta(hours=7)).hour  # Mountain Time
    if current_hour >= 20 or current_hour < 8:
        # Schedule for 8am
        next_time = datetime.now().replace(hour=8, minute=0, second=0)
        if current_hour >= 20:
            next_time += timedelta(days=1)
        
        scheduler.add_job(
            lambda: asyncio.run(send_scheduled_dom_message()),
            trigger="date",
            run_date=next_time,
            id="dom_message",
            replace_existing=True,
        )
        logger.info(f"Night mode active. Next message at 8am.")
        return
    
    minutes = random.randint(params.min_interval_minutes, params.max_interval_minutes)
    scheduler.add_job(
        lambda: asyncio.run(send_scheduled_dom_message()),
        trigger=IntervalTrigger(minutes=minutes),
        id="dom_message",
        replace_existing=True,
    )
    logger.info(f"Next message in {minutes} minutes")


async def send_scheduled_dom_message():
    """Send scheduled message"""
    db = SessionLocal()
    try:
        user = get_or_create_user(db, USER_CHAT_ID)
        params = user.parameters
        
        # Night mode check
        from datetime import timedelta
        current_hour = (datetime.utcnow() - timedelta(hours=7)).hour  # Mountain Time
        if current_hour >= 20 or current_hour < 8:
            return
        
        if user.safe_word_active and user.safe_word_until and datetime.utcnow() < user.safe_word_until:
            return
        
        if user.rest_day_until and datetime.utcnow() < user.rest_day_until:
            return
        
        # Check location stale
        location_stale = False
        if user.last_location_update:
            hours_since = (datetime.utcnow() - user.last_location_update).total_seconds() / 3600
            if hours_since > params.stale_location_hours:
                location_stale = True
        
        if location_stale:
            keyboard = [
                [InlineKeyboardButton("🏠 Home", callback_data="loc_home")],
                [InlineKeyboardButton("💼 Work", callback_data="loc_work")],
                [InlineKeyboardButton("🌆 Public", callback_data="loc_public")],
            ]
            await bot.send_message(
                chat_id=USER_CHAT_ID,
                text=f"📍 I don't know where you are (last updated {int(hours_since)} hours ago).\n\nTell me before I give you your next task.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return
        
        # Determine if task or conversation
        is_task = random.random() > params.conversation_ratio
        
        if is_task:
            # Generate task
            location = LocationType(user.current_location) if user.current_location else LocationType.PUBLIC
            task_data = generate_task_for_location(user, location, db)
            
            deadline = datetime.utcnow() + timedelta(minutes=params.task_timeout_minutes)
            task = Task(
                user_id=user.id,
                description=task_data["description"],
                task_type=task_data["task_type"],
                requires_photo=task_data["requires_photo"],
                intensity=task_data["difficulty"],
                deadline=deadline,
                is_extended_hold=task_data.get("is_extended_hold", False),
                location_type=task_data.get("location_type", location.value),
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            
            user.total_tasks += 1
            user.awaiting_response = True
            user.current_task_id = task.id
            
            keyboard = [
                [InlineKeyboardButton("✓ Task Complete", callback_data=f"complete_{task.id}")],
                [InlineKeyboardButton("✗ I Failed", callback_data=f"fail_{task.id}")],
            ]
            
            mood = AvatarMood.COMMANDING
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            
            full_message = f"📋 SCHEDULED TASK:\\n{task_data['description']}\\n\\n⏰ Deadline: {params.task_timeout_minutes} minutes\\n\\n📸 PHOTO PROOF REQUIRED"
            
            dom_msg = ConversationMessage(
                user_id=user.id,
                message=full_message,
                is_from_dom=True,
                has_avatar=True,
            )
            db.add(dom_msg)
            db.commit()
            
            if image_data:
                await bot.send_photo(
                    chat_id=USER_CHAT_ID,
                    photo=InputFile(io.BytesIO(image_data), filename="task.jpg"),
                    caption=full_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                await bot.send_message(
                    chat_id=USER_CHAT_ID,
                    text=full_message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            
            if task_data.get("is_extended_hold"):
                await schedule_task_checkins(user, task, db)
            
            scheduler.add_job(
                lambda: asyncio.run(check_escalation_wrapper(USER_CHAT_ID)),
                trigger=IntervalTrigger(minutes=params.task_timeout_minutes),
                id=f"escalation_check_{USER_CHAT_ID}",
                replace_existing=True,
            )
        else:
            # Conversation mode
            ai_response = generate_conversation_response(user, db)
            
            dom_msg = ConversationMessage(
                user_id=user.id,
                message=ai_response,
                is_from_dom=True,
                has_avatar=True,
            )
            db.add(dom_msg)
            db.commit()
            
            mood = random.choice([AvatarMood.FLIRTY, AvatarMood.CURIOUS, AvatarMood.MOCKING])
            image_data = AvatarGenerator.generate_avatar(user, mood, db)
            
            if image_data:
                await bot.send_photo(
                    chat_id=USER_CHAT_ID,
                    photo=InputFile(io.BytesIO(image_data), filename="dom_chat.jpg"),
                    caption=ai_response,
                )
            else:
                await bot.send_message(chat_id=USER_CHAT_ID, text=ai_response)
        
        schedule_next_message()
        
    except Exception as e:
        logger.error(f"Scheduled message error: {e}")
    finally:
        db.close()


def escalate_intensity(current: IntensityLevel) -> IntensityLevel:
    levels = list(IntensityLevel)
    idx = levels.index(current)
    return levels[idx + 1] if idx < len(levels) - 1 else current


def deescalate_intensity(current: IntensityLevel) -> IntensityLevel:
    levels = list(IntensityLevel)
    idx = levels.index(current)
    return levels[idx - 1] if idx > 0 else current


# ============================================================================
# MAIN
# ============================================================================

def main():
    scheduler.start()
    schedule_next_message()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("location", location_command))
    application.add_handler(CommandHandler("rewards", rewards_command))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CommandHandler("selfie", selfie_command))
    application.add_handler(CommandHandler("avatar", avatar_command))
    application.add_handler(CommandHandler("analyze", analyze_command))
    application.add_handler(CommandHandler("privileges", privileges_command))
    application.add_handler(CommandHandler("release", release_command))
    
    # Callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.PHOTO, enhanced_photo_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("Dom Bot v2.0 started. I am watching...")
    application.run_polling()


if __name__ == "__main__":
    main()