import os
import json
import logging
import asyncio
import base64
import random
import requests
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, DateTime, Boolean, Text, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ============ CONFIG ============
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
VENICE_API_KEY = os.getenv('VENICE_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
VENICE_API_URL = "https://api.venice.ai/api/v1"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"

# ============ DATABASE ============
Base = declarative_base()

class UserState(Base):
    __tablename__ = 'user_states'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(100))
    gender = Column(String(20), default=None)
    current_outfit = Column(String(100), default=None)
    outfit_items = Column(Text, default=None)
    location = Column(String(50), default=None)
    custom_location = Column(String(100), default=None)
    context_alone = Column(Boolean, default=True)
    context_others = Column(String(100), default=None)
    context_privacy = Column(String(20), default='private')
    risk_level = Column(Integer, default=1)
    points = Column(Integer, default=0)
    streak = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_task_at = Column(DateTime(timezone=True), nullable=True)
    next_task_time = Column(DateTime(timezone=True), nullable=True)
    scheduling_enabled = Column(Boolean, default=False)
    min_interval = Column(Integer, default=60)
    max_interval = Column(Integer, default=180)
    avatar_url = Column(Text, nullable=True)
    # Kinks
    kink_exposure = Column(Boolean, default=False)
    kink_humiliation = Column(Boolean, default=False)
    kink_degradation = Column(Boolean, default=False)
    kink_bondage = Column(Boolean, default=False)
    kink_pain = Column(Boolean, default=False)
    kink_service = Column(Boolean, default=False)
    kink_edging = Column(Boolean, default=False)
    kink_watersports = Column(Boolean, default=False)
    kink_exhibitionism = Column(Boolean, default=False)
    kink_roleplay = Column(Boolean, default=False)
    kink_petplay = Column(Boolean, default=False)
    kink_feminization = Column(Boolean, default=False)
    kink_cbt = Column(Boolean, default=False)
    kink_breathplay = Column(Boolean, default=False)
    kink_sensory = Column(Boolean, default=False)
    kink_temperature = Column(Boolean, default=False)
    kink_marking = Column(Boolean, default=False)
    kink_spanking = Column(Boolean, default=False)
    kink_nipple = Column(Boolean, default=False)
    kink_anal = Column(Boolean, default=False)
    kink_gags = Column(Boolean, default=False)
    kink_social_media = Column(Boolean, default=False)

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    task_text = Column(Text, nullable=False)
    risk_level = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    photo_url = Column(Text, nullable=True)
    verification_attempts = Column(Integer, default=0)

class TaskHistory(Base):
    __tablename__ = 'task_history'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    task_text = Column(Text, nullable=False)
    risk_level = Column(Integer, nullable=False)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AvatarImage(Base):
    __tablename__ = 'avatar_images'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    image_url = Column(Text, nullable=False)
    gender = Column(String(20))
    body_type = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# ============ CONSTANTS ============
RISK_LEVELS = {
    1: {"name": "Safe", "description": "Private, no exposure"},
    2: {"name": "Low Risk", "description": "Minimal exposure"},
    3: {"name": "Medium Risk", "description": "Empty public spaces"},
    4: {"name": "High Risk", "description": "Public with escape"},
    5: {"name": "Extreme Risk", "description": "Likely to be caught"}
}

KINK_CATEGORIES = {
    "kink_exposure": "📸 Exposure", "kink_humiliation": "😳 Humiliation",
    "kink_degradation": "🗑️ Degradation", "kink_bondage": "⛓️ Bondage",
    "kink_pain": "🔥 Pain", "kink_service": "🙇 Service",
    "kink_edging": "⏱️ Edging", "kink_watersports": "💧 Watersports",
    "kink_exhibitionism": "🎭 Exhibitionism", "kink_roleplay": "🎪 Roleplay",
    "kink_petplay": "🐾 Pet Play", "kink_feminization": "💄 Feminization",
    "kink_cbt": "🔩 CBT", "kink_breathplay": "😮‍💨 Breath Play",
    "kink_sensory": "🙈 Sensory", "kink_temperature": "🌡️ Temperature",
    "kink_marking": "✏️ Marking", "kink_spanking": "👋 Spanking",
    "kink_nipple": "👀 Nipple", "kink_anal": "🍑 Anal",
    "kink_gags": "🔇 Gags", "kink_social_media": "📱 Social Media"
}

OUTFIT_OPTIONS = {
    "casual": {"emoji": "👕", "name": "Casual", "male_items": ["t-shirt", "jeans", "boxers"], "female_items": ["t-shirt", "leggings", "panties"]},
    "formal": {"emoji": "👔", "name": "Formal", "male_items": ["button-up", "dress pants", "tie"], "female_items": ["blouse", "skirt", "bra"]},
    "athletic": {"emoji": "🎽", "name": "Athletic", "male_items": ["tank", "shorts", "compression"], "female_items": ["sports bra", "shorts", "panties"]},
    "lounge": {"emoji": "🛋️", "name": "Lounge", "male_items": ["hoodie", "sweatpants", "boxers"], "female_items": ["hoodie", "leggings", "panties"]},
    "minimal": {"emoji": "🩳", "name": "Underwear Only", "male_items": ["boxers"], "female_items": ["bra", "panties"]},
    "custom": {"emoji": "✏️", "name": "Custom", "male_items": [], "female_items": []}
}

GENDER_GUIDELINES = {
    "male": {"body_parts": ["chest", "abs", "cock", "balls", "ass"], "cannot": ["cleavage", "bra", "panties"]},
    "female": {"body_parts": ["cleavage", "breasts", "nipples", "pussy", "ass"], "cannot": ["cock", "balls"]},
    "trans": {"body_parts": ["chest", "breasts", "cock", "pussy", "ass"], "cannot": []},
    "nonbinary": {"body_parts": ["chest", "breasts", "genitals", "ass"], "cannot": []}
}

CONTEXT_OPTIONS = {
    "alone": {"emoji": "🧍", "name": "Alone", "bonus": 0},
    "partner": {"emoji": "💑", "name": "Partner Home", "bonus": 1},
    "roommates": {"emoji": "🏠", "name": "Roommates", "bonus": 1},
    "parents": {"emoji": "👨‍👩‍👧", "name": "Family", "bonus": 2},
    "kids": {"emoji": "👶", "name": "Kids Present", "bonus": 3},
    "friends": {"emoji": "🎉", "name": "Friends Over", "bonus": 1},
    "public": {"emoji": "👥", "name": "Public/Strangers", "bonus": 0}
}

# ============ HELPERS ============
def get_user_kinks(user):
    return [k.replace("kink_", "") for k in KINK_CATEGORIES if getattr(user, k, False)]

async def generate_ai_response(prompt, temperature=0.8):
    try:
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "claude-opus-4-8-fast",
            "messages": [
                {"role": "system", "content": "You are a dominant AI creating BDSM tasks. Be creative and demanding. No time durations - single actions proven by photo only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 500
        }
        response = requests.post(f"{VENICE_API_URL}/chat/completions", headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        logger.error(f"AI error: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"AI error: {e}")
        return None

async def analyze_image(image_bytes, task_desc):
    try:
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        data = {
            "model": "claude-opus-4-8-fast",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Task: {task_desc}\n\nDoes this photo show completion? Reply VERIFIED: yes/no REASON: brief"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }],
            "max_tokens": 200
        }
        response = requests.post(f"{VENICE_API_URL}/chat/completions", headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return "VERIFIED: no REASON: Error"
    except Exception as e:
        logger.error(f"Vision error: {e}")
        return "VERIFIED: no REASON: Error"

def parse_verification(response):
    verified = "yes" if "VERIFIED: yes" in response or "verified: yes" in response.lower() else "no"
    reason = response.split("REASON:")[1].strip() if "REASON:" in response else "Unknown"
    return verified, reason

async def generate_task_text(user):
    """AI generates task in real-time based on all context"""
    outfit_items = json.loads(user.outfit_items or '[]')
    gender = user.gender or "nonbinary"
    base_risk = user.risk_level or 1
    kinks = get_user_kinks(user)
    
    # Location context
    location = user.custom_location or user.location or "Unknown"
    others = user.context_others or "alone"
    privacy = user.context_privacy or "private"
    
    # Calculate effective risk
    bonus = CONTEXT_OPTIONS.get(others, {}).get("bonus", 0)
    if others == "kids":
        effective_risk = min(2, base_risk)  # Hard cap with kids
    else:
        privacy_mod = 1 if privacy == "exposed" else 0
        effective_risk = min(5, base_risk + bonus + privacy_mod)
    
    items_text = ", ".join(outfit_items) if outfit_items else "clothing"
    guide = GENDER_GUIDELINES.get(gender, GENDER_GUIDELINES["nonbinary"])
    body_parts = ", ".join(guide["body_parts"])
    cannot = ", ".join(guide["cannot_do"]) if guide["cannot_do"] else "none"
    kink_text = f"\nKinks: {', '.join(kinks)}" if kinks else ""
    
    # Build AI prompt with ALL context
    prompt = f"""Generate ONE BDSM exposure task for a {gender} submissive.

USER'S EXACT LOCATION: "{location}"
WHO IS PRESENT: {others}
PRIVACY LEVEL: {privacy}
BASE RISK LEVEL: {base_risk}
EFFECTIVE RISK: {effective_risk}

CURRENT OUTFIT: {user.current_outfit}
AVAILABLE CLOTHING: {items_text}
AVAILABLE BODY PARTS: {body_parts}
NEVER INCLUDE: {cannot}{kink_text}

RULES:
- Task MUST work at: {location}
- Respect presence of: {others} (effective risk: {effective_risk})
- NO time durations (no "for 5 minutes")
- Single action, photo proves completion
- Only use available clothing items
- Only reference body parts this gender has
- Never involve non-consenting people

The user described their location as: "{location}"
Use this to determine available spaces, privacy, and appropriate tasks.

Generate a specific, creative task for this exact situation:"""
    
    response = await generate_ai_response(prompt)
    if response:
        # Post-filter marking
        if "kink_marking" not in kinks:
            marking_words = ["write", "marker", "sharpie", "draw on", "body writing"]
            if any(w in response.lower() for w in marking_words):
                return f"Strip at {location} and photograph your {random.choice(guide['body_parts'][:3])}"
        return response.strip()
    return f"Strip completely at {location} and take a photo."

# ============ COMMANDS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "sub"
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            user = UserState(user_id=user_id, username=username)
            session.add(user)
            session.commit()
            
            keyboard = [
                [InlineKeyboardButton("👨 Male", callback_data="gender_male")],
                [InlineKeyboardButton("👩 Female", callback_data="gender_female")],
                [InlineKeyboardButton("⚧ Trans", callback_data="gender_trans")],
                [InlineKeyboardButton("🌈 Non-binary", callback_data="gender_nonbinary")]
            ]
            await update.message.reply_text(f"Welcome, {username}. Select gender:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        loc = user.custom_location or user.location or "Not set"
        await update.message.reply_text(
            f"Welcome back, {username}!\n\n"
            f"Gender: {user.gender or 'Not set'}\n"
            f"Location: {loc}\n"
            f"Risk: {user.risk_level}\n"
            f"Points: {user.points} | Streak: {user.streak}\n\n"
            f"/task - Get challenge\n"
            f"/wherenow - Set location\n"
            f"/outfit - Set clothing\n"
            f"/gender - Change gender\n"
            f"/risk - Set risk (1-5)\n"
            f"/kinks - Toggle kinks\n"
            f"/status - Check task\n"
            f"/schedule - Auto-tasks\n"
            f"/reward - Avatar rewards"
        )
    finally:
        session.close()

async def gender_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👨 Male", callback_data="gender_male")],
        [InlineKeyboardButton("👩 Female", callback_data="gender_female")],
        [InlineKeyboardButton("⚧ Trans", callback_data="gender_trans")],
        [InlineKeyboardButton("🌈 Non-binary", callback_data="gender_nonbinary")]
    ]
    await update.message.reply_text("Select gender:", reply_markup=InlineKeyboardMarkup(keyboard))

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("gender_", "")
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.gender = gender
            session.commit()
            emoji = {"male": "👨", "female": "👩", "trans": "⚧", "nonbinary": "🌈"}.get(gender, "❓")
            await query.edit_message_text(f"{emoji} Gender: {gender.capitalize()}\n\nUse /outfit to set clothing.")
    finally:
        session.close()

async def outfit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user or not user.gender:
            await update.message.reply_text("Set gender first with /gender")
            return
        
        keyboard = [[InlineKeyboardButton(f"{o['emoji']} {o['name']}", callback_data=f"outfit_{k}")] for k, o in OUTFIT_OPTIONS.items()]
        current = user.current_outfit or "Not set"
        await update.message.reply_text(f"Current: {current}\n\nWhat are you wearing?", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

async def outfit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    outfit_key = query.data.replace("outfit_", "")
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        
        if outfit_key == "custom":
            context.user_data['awaiting_custom_outfit'] = True
            await query.edit_message_text("Describe your outfit (e.g., 'White tank, grey sweatpants'):")
            return
        
        outfit = OUTFIT_OPTIONS[outfit_key]
        items = outfit.get(f"{user.gender}_items", outfit["male_items"])
        user.current_outfit = outfit["name"]
        user.outfit_items = json.dumps(items)
        session.commit()
        
        items_text = "\n".join([f"  • {i}" for i in items])
        await query.edit_message_text(f"{outfit['emoji']} Outfit: {outfit['name']}\n\nItems:\n{items_text}\n\nUse /wherenow to set location!")
    finally:
        session.close()

async def handle_custom_outfit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_custom_outfit'):
        return
    
    user_id = update.effective_user.id
    custom = update.message.text
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.current_outfit = f"Custom: {custom[:50]}"
            items = [i.strip() for i in custom.split(',')]
            user.outfit_items = json.dumps(items[:6])
            session.commit()
            await update.message.reply_text("✅ Outfit saved. Use /wherenow to set your location!")
    finally:
        session.close()
    
    context.user_data['awaiting_custom_outfit'] = False

async def wherenow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set specific location and context"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🏪 Store/Shop", callback_data="ctx_store")],
        [InlineKeyboardButton("🏠 Home", callback_data="ctx_home")],
        [InlineKeyboardButton("🏨 Hotel", callback_data="ctx_hotel")],
        [InlineKeyboardButton("🚗 Vehicle", callback_data="ctx_car")],
        [InlineKeyboardButton("🏢 Work", callback_data="ctx_work")],
        [InlineKeyboardButton("🌳 Outdoors", callback_data="ctx_outdoor")],
        [InlineKeyboardButton("✏️ Other/Custom", callback_data="ctx_custom")]
    ]
    
    await update.message.reply_text(
        "📍 Where are you right now?\n\n"
        "Be specific - 'Target fitting rooms', 'Home Depot aisle 12', 'Parents basement'\n\n"
        "Or pick a category:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def context_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    ctx_type = query.data.replace("ctx_", "")
    
    if ctx_type == "custom":
        context.user_data['awaiting_custom_location'] = True
        await query.edit_message_text(
            "Describe exactly where you are:\n\n"
            "Examples:\n"
            "• 'Target, dressing room area, few people'\n"
            "• 'Home Depot lumber aisle, mostly empty'\n"
            "• 'Parents house, basement, they're upstairs'\n"
            "• 'Car in mall parking lot, level 3'\n"
            "• 'Gas station bathroom, single room'"
        )
        return
    
    # Predefined
    loc_map = {
        "store": "Retail Store", "home": "Home", "hotel": "Hotel",
        "car": "Vehicle", "work": "Work", "outdoor": "Outdoors"
    }
    location = loc_map.get(ctx_type, "Unknown")
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.location = location
            user.custom_location = location
            session.commit()
    finally:
        session.close()
    
    # Ask who is present
    keyboard = [
        [InlineKeyboardButton("🧍 Alone", callback_data="present_alone")],
        [InlineKeyboardButton("💑 Partner", callback_data="present_partner")],
        [InlineKeyboardButton("🏠 Roommates", callback_data="present_roommates")],
        [InlineKeyboardButton("👨‍👩‍👧 Family", callback_data="present_parents")],
        [InlineKeyboardButton("👶 Kids Present", callback_data="present_kids")],
        [InlineKeyboardButton("🎉 Friends", callback_data="present_friends")],
        [InlineKeyboardButton("👥 Public/Strangers", callback_data="present_public")]
    ]
    
    await query.edit_message_text(
        f"📍 Location: {location}\n\n"
        f"Who is present or nearby?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def present_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    present_type = query.data.replace("present_", "")
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        
        user.context_others = present_type
        user.context_alone = (present_type == "alone")
        
        # Kids = hard limit
        if present_type == "kids":
            if user.risk_level > 2:
                user.risk_level = 2
        
        session.commit()
    finally:
        session.close()
    
    # Ask privacy level
    keyboard = [
        [InlineKeyboardButton("🔒 Private (locked door)", callback_data="privacy_private")],
        [InlineKeyboardButton("🚪 Semi-private (door closed)", callback_data="privacy_semi")],
        [InlineKeyboardButton("👁️ Exposed (could be seen)", callback_data="privacy_exposed")],
        [InlineKeyboardButton("🌍 Public (full view)", callback_data="privacy_public")]
    ]
    
    ctx_name = CONTEXT_OPTIONS.get(present_type, {}).get("name", present_type)
    await query.edit_message_text(
        f"👥 Context: {ctx_name}\n\n"
        f"What's your privacy level?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def privacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    privacy = query.data.replace("privacy_", "")
    
    privacy_names = {
        "private": "🔒 Private (locked)", "semi": "🚪 Semi-private",
        "exposed": "👁️ Exposed", "public": "🌍 Public"
    }
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.context_privacy = privacy
            session.commit()
            
            base = user.risk_level
            others = user.context_others or "alone"
            bonus = CONTEXT_OPTIONS.get(others, {}).get("bonus", 0)
            
            if others == "kids":
                effective = min(2, base)
            else:
                mod = 1 if privacy == "exposed" else 0
                effective = min(5, base + bonus + mod)
            
            loc = user.custom_location or user.location or "Not set"
            
            await query.edit_message_text(
                f"✅ Context Set!\n\n"
                f"📍 Location: {loc}\n"
                f"👥 Present: {CONTEXT_OPTIONS.get(others, {}).get('name', 'Alone')}\n"
                f"🔒 Privacy: {privacy_names.get(privacy, privacy)}\n"
                f"🎯 Effective Risk: {effective}\n\n"
                f"Use /task for location-aware challenges!"
            )
    finally:
        session.close()

async def handle_custom_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_custom_location'):
        return
    
    user_id = update.effective_user.id
    location = update.message.text
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.custom_location = location[:100]
            user.location = "Custom"
            session.commit()
            
            keyboard = [
                [InlineKeyboardButton("🧍 Alone", callback_data="present_alone")],
                [InlineKeyboardButton("💑 Partner", callback_data="present_partner")],
                [InlineKeyboardButton("🏠 Roommates", callback_data="present_roommates")],
                [InlineKeyboardButton("👨‍👩‍👧 Family", callback_data="present_parents")],
                [InlineKeyboardButton("👶 Kids", callback_data="present_kids")],
                [InlineKeyboardButton("👥 Public", callback_data="present_public")]
            ]
            
            await update.message.reply_text(
                f"📍 Location: {location}\n\n"
                f"Who is present?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    finally:
        session.close()
    
    context.user_data['awaiting_custom_location'] = False

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(f"{i}️⃣ {RISK_LEVELS[i]['name']}", callback_data=f"risk_{i}")] for i in range(1, 6)]
    await update.message.reply_text("Select risk level:", reply_markup=InlineKeyboardMarkup(keyboard))

async def risk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    risk = int(query.data.replace("risk_", ""))
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.risk_level = risk
            session.commit()
            await query.edit_message_text(f"Risk {risk}: {RISK_LEVELS[risk]['name']}")
    finally:
        session.close()

async def kinks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        keyboard = []
        for key, name in KINK_CATEGORIES.items():
            enabled = getattr(user, key, False)
            keyboard.append([InlineKeyboardButton(f"{'✅' if enabled else '❌'} {name}", callback_data=f"toggle_{key}")])
        keyboard.append([InlineKeyboardButton("🔙 Done", callback_data="kinks_done")])
        
        await update.message.reply_text("Toggle kinks:", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

async def toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "kinks_done":
        await query.edit_message_text("Kinks updated! Use /task.")
        return
    
    kink_key = query.data.replace("toggle_", "")
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user and hasattr(user, kink_key):
            setattr(user, kink_key, not getattr(user, kink_key, False))
            session.commit()
            
            keyboard = []
            for key, name in KINK_CATEGORIES.items():
                enabled = getattr(user, key, False)
                keyboard.append([InlineKeyboardButton(f"{'✅' if enabled else '❌'} {name}", callback_data=f"toggle_{key}")])
            keyboard.append([InlineKeyboardButton("🔙 Done", callback_data="kinks_done")])
            await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        if not user.gender:
            await gender_cmd(update, context)
            return
        if not user.current_outfit:
            await outfit_cmd(update, context)
            return
        if not user.custom_location:
            await wherenow_cmd(update, context)
            return
        
        active = session.query(Task).filter_by(user_id=user_id, status="pending").first()
        if active:
            time_left = (active.expires_at - datetime.now(timezone.utc)).total_seconds() / 60
            await update.message.reply_text(f"Active task!\n\n{active.task_text[:200]}...\n\nTime: {max(0, time_left):.0f} min left")
            return
        
        await update.message.reply_text("🤖 AI generating your custom task...")
        
        # AI generates task in real-time
        task_text = await generate_task_text(user)
        
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=30)
        
        task = Task(user_id=user_id, task_text=task_text, risk_level=user.risk_level, created_at=now, expires_at=expires)
        session.add(task)
        session.commit()
        
        # Schedule timeout
        scheduler.add_job(
            auto_clear_task,
            'date',
            run_date=expires,
            args=[user_id, task.id],
            id=f"timeout_{task.id}",
            replace_existing=True
        )
        
        others = user.context_others or "alone"
        effective = user.risk_level + CONTEXT_OPTIONS.get(others, {}).get("bonus", 0)
        if others == "kids":
            effective = min(2, user.risk_level)
        effective = min(5, effective)
        
        keyboard = [
            [InlineKeyboardButton("📸 Send Photo", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
        ]
        
        loc = user.custom_location or user.location
        
        await update.message.reply_text(
            f"🎯 TASK (Base Risk {user.risk_level}, Effective {effective})\n\n"
            f"📍 {loc}\n"
            f"👔 {user.current_outfit}\n\n"
            f"{task_text}\n\n"
            f"Complete and send photo. 30 minutes.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        active = session.query(Task).filter_by(user_id=user_id, status="pending").first()
        if active:
            time_left = (active.expires_at - datetime.now(timezone.utc)).total_seconds() / 60
            keyboard = [
                [InlineKeyboardButton("📸 Complete", callback_data=f"complete_{active.id}")],
                [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{active.id}")]
            ]
            await update.message.reply_text(
                f"🎯 ACTIVE TASK\n\n{active.task_text[:200]}...\n\n⏰ {max(0, time_left):.0f} min left\nSend photo.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            loc = user.custom_location or user.location or "Not set"
            await update.message.reply_text(
                f"No active task.\n\n"
                f"📍 Location: {loc}\n"
                f"Points: {user.points} | Streak: {user.streak}\n"
                f"Risk: {user.risk_level}\n\n"
                f"Use /task!"
            )
    finally:
        session.close()

# ============ PHOTO HANDLING ============
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        task = session.query(Task).filter_by(user_id=user_id, status="pending").first()
        if not task:
            await update.message.reply_text("No active task. Use /task.")
            return
        
        now = datetime.now(timezone.utc)
        if now > task.expires_at:
            task.status = "expired"
            session.commit()
            await update.message.reply_text("⏰ Task expired. Use /task.")
            return
        
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        await update.message.reply_text("📸 AI analyzing your photo...")
        photo_bytes = await file.download_as_bytearray()
        
        if len(photo_bytes) < 1000:
            await update.message.reply_text("Photo too small. Send clearer photo.")
            return
        
        verification = await analyze_image(photo_bytes, task.task_text)
        verified, reason = parse_verification(verification)
        task.verification_attempts += 1
        
        if verified == "yes":
            task.status = "completed"
            task.completed_at = now
            
            user = session.query(UserState).filter_by(user_id=user_id).first()
            user.points += 10 * task.risk_level
            user.streak += 1
            user.completed_tasks += 1
            user.consecutive_failures = 0
            session.commit()
            
            reward = "\n\n🎁 REWARD! Use /reward." if user.completed_tasks % 5 == 0 else ""
            await update.message.reply_text(
                f"✅ COMPLETED!\n\n"
                f"+{10 * task.risk_level} points\n"
                f"Streak: {user.streak}\n"
                f"Total: {user.points}{reward}"
            )
        else:
            if task.verification_attempts >= 2:
                task.status = "failed"
                user = session.query(UserState).filter_by(user_id=user_id).first()
                user.consecutive_failures += 1
                session.commit()
                await update.message.reply_text(f"❌ FAILED\n\nReason: {reason}\nNo retries left. Use /task.")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔄 Try Again", callback_data=f"retry_{task.id}")],
                    [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
                ]
                await update.message.reply_text(
                    f"❌ Rejected: {reason}\n\n{2 - task.verification_attempts} retry left.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        
        session.commit()
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await update.message.reply_text("Error processing photo. Try again.")
    finally:
        session.close()

async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Send your photo proof now.")

async def giveup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.replace("giveup_", ""))
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id, user_id=user_id).first()
        if task and task.status == "pending":
            task.status = "failed"
            user = session.query(UserState).filter_by(user_id=user_id).first()
            user.points = max(0, user.points - 5)
            user.streak = 0
            session.commit()
            await query.edit_message_text("❌ Task abandoned. -5 points. Use /task.")
    finally:
        session.close()

async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Send retry photo now.")

async def auto_clear_task(user_id, task_id):
    logger.info(f"Timeout task {task_id}")
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id).first()
        if not task or task.status != "pending":
            return
        
        task.status = "expired"
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.points = max(0, user.points - 10)
            user.streak = 0
            user.consecutive_failures += 1
            session.commit()
            
            try:
                app = Application.builder().token(TELEGRAM_TOKEN).build()
                await app.bot.send_message(chat_id=user_id, text="⏰ TASK EXPIRED\n-10 points. Use /task.")
            except Exception as e:
                logger.error(f"Notify error: {e}")
        session.commit()
    except Exception as e:
        logger.error(f"Auto-clear error: {e}")
    finally:
        session.close()

# ============ SCHEDULER ============
scheduler = AsyncIOScheduler()

async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("▶️ Enable", callback_data="sched_enable")],
        [InlineKeyboardButton("⏹️ Disable", callback_data="sched_disable")]
    ]
    await update.message.reply_text("Auto-Task Scheduler:", reply_markup=InlineKeyboardMarkup(keyboard))

async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        
        if query.data == "sched_enable":
            user.scheduling_enabled = True
            user.next_task_time = datetime.now(timezone.utc) + timedelta(minutes=random.randint(user.min_interval, user.max_interval))
            session.commit()
            await query.edit_message_text("✅ Auto-tasks enabled!")
        elif query.data == "sched_disable":
            user.scheduling_enabled = False
            user.next_task_time = None
            session.commit()
            await query.edit_message_text("⏹️ Auto-tasks disabled.")
    finally:
        session.close()

async def random_interval_check():
    session = get_session()
    try:
        now = datetime.now(timezone.utc)
        users = session.query(UserState).filter(UserState.scheduling_enabled == True, UserState.next_task_time <= now).all()
        
        for user in users:
            active = session.query(Task).filter_by(user_id=user.user_id, status="pending").first()
            if not active:
                try:
                    app = Application.builder().token(TELEGRAM_TOKEN).build()
                    task_text = await generate_task_text(user)
                    
                    expires = now + timedelta(minutes=30)
                    task = Task(user_id=user.user_id, task_text=task_text, risk_level=user.risk_level, created_at=now, expires_at=expires)
                    session.add(task)
                    session.commit()
                    
                    scheduler.add_job(
                        auto_clear_task,
                        'date',
                        run_date=expires,
                        args=[user.user_id, task.id],
                        id=f"timeout_{task.id}",
                        replace_existing=True
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("📸 Send Photo", callback_data=f"complete_{task.id}")],
                        [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
                    ]
                    await app.bot.send_message(
                        chat_id=user.user_id,
                        text=f"🎯 AUTO TASK (Risk {user.risk_level})\n\n{task_text}\n\n30 minutes.",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                    user.next_task_time = now + timedelta(minutes=random.randint(user.min_interval, user.max_interval))
                    session.commit()
                except Exception as e:
                    logger.error(f"Auto-task error: {e}")
    except Exception as e:
        logger.error(f"Interval check error: {e}")
    finally:
        session.close()

# ============ REWARD ============
async def reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user or not user.gender:
            await update.message.reply_text("Set gender with /gender first")
            return
        
        if user.completed_tasks < 5:
            needed = 5 - (user.completed_tasks % 5)
            await update.message.reply_text(f"Complete {needed} more tasks for reward!")
            return
        
        await update.message.reply_text("🎨 Generating reward...")
        
        gender_desc = {"male": "male", "female": "female", "trans": "trans feminine", "nonbinary": "androgynous"}.get(user.gender, "person")
        prompt = f"Beautiful {gender_desc}, nude, erotic, submissive, high quality"
        
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "chroma", "prompt": prompt, "width": 512, "height": 768, "seed": random.randint(1, 1000000)}
        
        response = requests.post(VENICE_IMAGE_URL, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if 'images' in result and result['images']:
                avatar = AvatarImage(user_id=user_id, image_url=result['images'][0], gender=user.gender)
                session.add(avatar)
                session.commit()
                await update.message.reply_photo(photo=result['images'][0], caption="🎁 Reward! Use /reward for another.")
            else:
                await update.message.reply_text("Generation failed. Try again.")
        else:
            await update.message.reply_text("Error. Try again.")
    except Exception as e:
        logger.error(f"Reward error: {e}")
        await update.message.reply_text("Error. Try again.")
    finally:
        session.close()

# ============ RESET ============
async def resetowner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚠️ YES DELETE ALL", callback_data="reset_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="reset_cancel")]
    ]
    await update.message.reply_text("⚠️ DELETE ALL DATA?\n\nThis cannot be undone!", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "reset_cancel":
        await query.edit_message_text("Reset cancelled.")
        return
    
    user_id = update.effective_user.id
    session = get_session()
    try:
        session.query(Task).filter_by(user_id=user_id).delete()
        session.query(TaskHistory).filter_by(user_id=user_id).delete()
        session.query(AvatarImage).filter_by(user_id=user_id).delete()
        session.query(UserState).filter_by(user_id=user_id).delete()
        session.commit()
        await query.edit_message_text("✅ All data deleted. Send /start.")
    except Exception as e:
        logger.error(f"Reset error: {e}")
        await query.edit_message_text("Error.")
    finally:
        session.close()

# ============ MAIN ============
def main():
    scheduler.start()
    scheduler.add_job(random_interval_check, IntervalTrigger(minutes=1), id="interval_check", replace_existing=True)
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("gender", gender_cmd))
    application.add_handler(CommandHandler("outfit", outfit_cmd))
    application.add_handler(CommandHandler("wherenow", wherenow_cmd))
    application.add_handler(CommandHandler("risk", risk_cmd))
    application.add_handler(CommandHandler("kinks", kinks_cmd))
    application.add_handler(CommandHandler("task", task_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("schedule", schedule_cmd))
    application.add_handler(CommandHandler("reward", reward_cmd))
    application.add_handler(CommandHandler("resetowner", resetowner_cmd))
    application.add_handler(CommandHandler("help", start))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    application.add_handler(CallbackQueryHandler(outfit_callback, pattern="^outfit_"))
    application.add_handler(CallbackQueryHandler(context_callback, pattern="^ctx_"))
    application.add_handler(CallbackQueryHandler(present_callback, pattern="^present_"))
    application.add_handler(CallbackQueryHandler(privacy_callback, pattern="^privacy_"))
    application.add_handler(CallbackQueryHandler(risk_callback, pattern="^risk_"))
    application.add_handler(CallbackQueryHandler(toggle_callback, pattern="^toggle_|^kinks_done"))
    application.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_"))
    application.add_handler(CallbackQueryHandler(giveup_callback, pattern="^giveup_"))
    application.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(schedule_callback, pattern="^sched_"))
    application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    
    # Messages
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Text handler for custom inputs
    async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('awaiting_custom_outfit'):
            await handle_custom_outfit(update, context)
        elif context.user_data.get('awaiting_custom_location'):
            await handle_custom_location(update, context)
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("DOM Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()