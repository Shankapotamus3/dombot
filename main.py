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
    # Avatar preferences
    avatar_gender = Column(String(20), default=None)
    avatar_race = Column(String(20), default=None)
    avatar_build = Column(String(20), default=None)
    avatar_hair = Column(String(20), default=None)
    avatar_genital_size = Column(String(20), default=None)
    # Reward tracking
    challenges_since_reward = Column(Integer, default=0)
    last_kinks_used = Column(Text, default=None)
    # Kinks - "no" = hard limit, "okay" = allowed, "yes" = desired
    kink_exposure = Column(String(10), default="no")
    kink_humiliation = Column(String(10), default="no")
    kink_degradation = Column(String(10), default="no")
    kink_bondage = Column(String(10), default="no")
    kink_pain = Column(String(10), default="no")
    kink_service = Column(String(10), default="no")
    kink_edging = Column(String(10), default="no")
    kink_watersports = Column(String(10), default="no")
    kink_exhibitionism = Column(String(10), default="no")
    kink_roleplay = Column(String(10), default="no")
    kink_petplay = Column(String(10), default="no")
    kink_feminization = Column(String(10), default="no")
    kink_cbt = Column(String(10), default="no")
    kink_breathplay = Column(String(10), default="no")
    kink_sensory = Column(String(10), default="no")
    kink_temperature = Column(String(10), default="no")
    kink_marking = Column(String(10), default="no")
    kink_spanking = Column(String(10), default="no")
    kink_nipple = Column(String(10), default="no")
    kink_anal = Column(String(10), default="no")
    kink_gags = Column(String(10), default="no")
    kink_social_media = Column(String(10), default="no")

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
    race = Column(String(20))
    build = Column(String(20))
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
    "kink_exposure": ("📸 Exposure", "Being seen/photographed"),
    "kink_humiliation": ("😳 Humiliation", "Verbal degradation, embarrassment"),
    "kink_degradation": ("🗑️ Degradation", "Being treated as inferior/object"),
    "kink_bondage": ("⛓️ Bondage", "Restraint, tied up"),
    "kink_pain": ("🔥 Pain", "Impact play, discomfort"),
    "kink_service": ("🙇 Service", "Serving, chores, tasks"),
    "kink_edging": ("⏱️ Edging", "Orgasm denial, control"),
    "kink_watersports": ("💧 Watersports", "Pee play"),
    "kink_exhibitionism": ("🎭 Exhibitionism", "Public exposure"),
    "kink_roleplay": ("🎪 Roleplay", "Scenarios, characters"),
    "kink_petplay": ("🐾 Pet Play", "Animal roleplay"),
    "kink_feminization": ("💄 Feminization", "Forced fem, sissy"),
    "kink_cbt": ("🔩 CBT", "Cock/ball torture"),
    "kink_breathplay": ("😮‍💨 Breath Play", "Choking, breath control"),
    "kink_sensory": ("🙈 Sensory", "Blindfolds, earplugs"),
    "kink_temperature": ("🌡️ Temperature", "Ice, heat, wax"),
    "kink_marking": ("✏️ Marking", "Writing, body writing"),
    "kink_spanking": ("👋 Spanking", "Slapping, impact"),
    "kink_nipple": ("👀 Nipple", "Nipple play, clamps"),
    "kink_anal": ("🍑 Anal", "Ass play, plugs"),
    "kink_gags": ("🔇 Gags", "Gags, mouth restriction"),
    "kink_social_media": ("📱 Social Media", "Online exposure/tasks")
}

KINK_LEVELS = {
    "no": {"emoji": "❌", "name": "No", "desc": "Hard limit - never"},
    "okay": {"emoji": "⭕", "name": "Okay", "desc": "Allowed - Dom decides"},
    "yes": {"emoji": "✅", "name": "Yes", "desc": "Desired - please include"}
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

AVATAR_GENDERS = {
    "male": {"emoji": "👨", "name": "Male", "desc": "Masculine, muscular or slim"},
    "female": {"emoji": "👩", "name": "Female", "desc": "Feminine, curvy or slim"},
    "trans": {"emoji": "⚧", "name": "Trans/Futa", "desc": "Feminine with penis and breasts"}
}

AVATAR_RACES = {
    "white": {"emoji": "🏻", "name": "White/Caucasian"},
    "black": {"emoji": "🏿", "name": "Black/African"},
    "asian": {"emoji": "🌸", "name": "Asian"},
    "hispanic": {"emoji": "🌶️", "name": "Hispanic/Latino"},
    "middle_eastern": {"emoji": "🕌", "name": "Middle Eastern"},
    "indian": {"emoji": "🪷", "name": "Indian/South Asian"}
}

AVATAR_BUILDS = {
    "slim": {"emoji": "🧍", "name": "Slim/Ectomorph", "desc": "extremely skinny, no muscle, petite, waif-like, bony, fragile"},
    "athletic": {"emoji": "💪", "name": "Athletic", "desc": "fit, toned, muscular definition"},
    "curvy": {"emoji": "🍑", "name": "Curvy", "desc": "full figured, wide hips, voluptuous"},
    "muscular": {"emoji": "🏋️", "name": "Muscular", "desc": "ripped, bodybuilder, strong"}
}

AVATAR_HAIR = {
    "blonde": "Blonde",
    "brunette": "Brunette",
    "black": "Black",
    "red": "Red",
    "pink": "Pink",
    "blue": "Blue",
    "purple": "Purple",
    "white": "White/Silver"
}

AVATAR_SIZES = {
    "small": {"emoji": "🔹", "name": "Small", "male": "small petite penis", "female": "small petite breasts", "trans": "small breasts and penis"},
    "medium": {"emoji": "🔸", "name": "Medium", "male": "medium sized penis", "female": "medium full breasts", "trans": "medium breasts and penis"},
    "large": {"emoji": "🔶", "name": "Large", "male": "large thick penis", "female": "large voluptuous breasts", "trans": "large breasts and penis"}
}

DOMINANT_POSES = [
    "standing with hands on hips, dominant stance",
    "sitting on throne-like chair, legs spread, commanding",
    "holding riding crop, stern expression",
    "crossed arms, looking down at camera, powerful",
    "holding leash, dominant posture",
    "standing over camera angle, feet visible, superior pose",
    "holding whip behind back, confident stance",
    "one foot on chair, elbow on knee, dominant",
    "finger pointing down, commanding gesture",
    "holding collar and leash, expectant expression"
]

DOMINANT_OUTFITS = [
    "latex catsuit",
    "leather corset and thigh boots",
    "dominatrix outfit with gloves",
    "sheer bodysuit with harness",
    "pvc dress with choker",
    "fishnet bodysuit with straps",
    "leather harness and panties",
    "lace lingerie with garter belt",
    "shiny metallic bikini",
    "strappy harness outfit"
]

# ============ HELPERS ============
def get_user_kinks(user, level=None):
    kinks = []
    for k in KINK_CATEGORIES.keys():
        kink_value = getattr(user, k, "no")
        if level is None and kink_value in ["yes", "okay"]:
            kinks.append(k.replace("kink_", ""))
        elif level and kink_value == level:
            kinks.append(k.replace("kink_", ""))
    return kinks

def get_kink_level(user, kink_name):
    full_name = f"kink_{kink_name}" if not kink_name.startswith("kink_") else kink_name
    return getattr(user, full_name, "no")

def get_title(avatar_gender):
    """Get appropriate title based on avatar gender"""
    return "Sir" if avatar_gender == "male" else "Mistress"

async def generate_ai_response(prompt, temperature=0.9):
    try:
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "claude-opus-4-8-fast",
            "messages": [
                {"role": "system", "content": "You are a playful but demanding Domme. Speak with confidence, occasional teasing, and personality. Be conversational, use pet names, mix encouragement with demands."},
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
        
        prompt = f"""Task: {task_desc}

Verify this photo. Be REASONABLE about:
- Selfie angles (can't see own face/back in selfie)
- Lighting and shadows
- Equivalent items (any clamp = clothespin, any tie = rope, etc.)

Does this show completion? Reply:
VERIFIED: yes/no
REASON: brief

Be lenient - if effort was made, verify yes."""
        
        data = {
            "model": "claude-opus-4-8-fast",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
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

async def generate_task_text(user, session=None):
    """Generate task with strict filtering"""
    outfit_items = json.loads(user.outfit_items or '[]')
    gender = user.gender or "nonbinary"
    base_risk = user.risk_level or 1
    
    location = user.custom_location or user.location or "Unknown"
    others = user.context_others or "alone"
    privacy = user.context_privacy or "private"
    
    bonus = CONTEXT_OPTIONS.get(others, {}).get("bonus", 0)
    if others == "kids":
        effective_risk = min(2, base_risk)
    else:
        privacy_mod = 1 if privacy == "exposed" else 0
        effective_risk = min(5, base_risk + bonus + privacy_mod)
    
    items_text = ", ".join(outfit_items) if outfit_items else "clothing"
    guide = GENDER_GUIDELINES.get(gender, GENDER_GUIDELINES["nonbinary"])
    body_parts = ", ".join(guide["body_parts"])
    cannot = ", ".join(guide.get("cannot", [])) if guide.get("cannot") else "none"
    
    yes_kinks = get_user_kinks(user, "yes")
    okay_kinks = get_user_kinks(user, "okay")
    
    forbidden_kinks = []
    for k in KINK_CATEGORIES.keys():
        if getattr(user, k, "no") == "no":
            forbidden_kinks.append(k.replace("kink_", ""))
    
    all_allowed = yes_kinks + okay_kinks
    
    if not all_allowed:
        return f"Strip completely at {location} and take a photo."
    
    selected_kinks = []
    if yes_kinks:
        selected_kinks.append(random.choice(yes_kinks))
        if len(yes_kinks) > 1 and random.random() < 0.5:
            remaining_yes = [k for k in yes_kinks if k not in selected_kinks]
            if remaining_yes:
                selected_kinks.append(random.choice(remaining_yes))
    
    remaining_slots = random.randint(1, 3) - len(selected_kinks)
    if remaining_slots > 0 and okay_kinks:
        available_okay = [k for k in okay_kinks if k not in selected_kinks]
        if available_okay:
            selected_kinks.extend(random.sample(available_okay, min(remaining_slots, len(available_okay))))
    
    user.last_kinks_used = json.dumps(selected_kinks[-4:])
    if session:
        session.commit()
    
    yes_text = f"\nDESIRED: {', '.join(yes_kinks)}" if yes_kinks else ""
    selected_text = f"\nUSE: {', '.join(selected_kinks)}"
    forbidden_text = f"\n\nNEVER: {', '.join(forbidden_kinks)}" if forbidden_kinks else ""
    
    prompt = f"""Create ONE BDSM task for a {gender} sub.

Location: {location}
Context: {others}, {privacy} privacy
Risk: {effective_risk}/5
Outfit: {user.current_outfit}
Items: {items_text}
Body parts: {body_parts}{yes_text}{selected_text}{forbidden_text}

Rules:
- Single action, photo proof
- No time durations
- Never use forbidden kinks
- Be creative and specific

Task:"""
    
    response = await generate_ai_response(prompt, temperature=0.9)
    
    if response:
        response = response.strip()
        
        forbidden_keywords = {
            "marking": ["write", "marker", "sharpie", "draw on", "body writing", "written", "label"],
            "watersports": ["pee", "piss", "urine", "wet yourself"],
            "breathplay": ["choke", "strangle", "suffocate"],
            "social_media": ["post", "upload", "instagram", "twitter", "facebook", "share online"]
        }
        
        for forbidden_kink, keywords in forbidden_keywords.items():
            if forbidden_kink in forbidden_kinks:
                if any(kw in response.lower() for kw in keywords):
                    logger.warning(f"Filtered forbidden kink '{forbidden_kink}'")
                    return await generate_task_text(user, session)
        
        return response
    
    return f"Strip at {location} and photograph your {random.choice(guide['body_parts'][:3])}"

# ============ AVATAR ============
async def generate_avatar_pose(user, pose_type="dominant"):
    try:
        gender = user.avatar_gender or user.gender or "female"
        race = user.avatar_race or "white"
        build = user.avatar_build or "curvy"
        hair = user.avatar_hair or "black"
        size = user.avatar_genital_size or "medium"
        
        race_desc = AVATAR_RACES.get(race, AVATAR_RACES["white"])["name"].split('/')[0]
        build_desc = AVATAR_BUILDS.get(build, AVATAR_BUILDS["curvy"])["desc"]
        size_desc = AVATAR_SIZES.get(size, AVATAR_SIZES["medium"]).get(gender, AVATAR_SIZES["medium"]["female"])
        
        if pose_type == "reward":
            prompt = f"Beautiful {race_desc} {gender}, {build_desc}, {hair} hair, {size_desc}, completely nude, erotic submissive pose, high quality, detailed skin"
        else:
            pose = random.choice(DOMINANT_POSES)
            outfit = random.choice(DOMINANT_OUTFITS)
            prompt = f"Beautiful {race_desc} {gender}, {build_desc}, {hair} hair, {size_desc}, wearing {outfit}, {pose}, dominant attitude, high quality"
        
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "chroma",
            "prompt": prompt,
            "width": 512,
            "height": 768,
            "seed": random.randint(1, 1000000)
        }
        
        response = requests.post(VENICE_IMAGE_URL, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if 'images' in result and result['images']:
                return result['images'][0]
        
        logger.error(f"Avatar failed: {response.status_code}")
        return None
        
    except Exception as e:
        logger.error(f"Avatar error: {e}")
        return None

async def generate_avatar_pose_image(gender, race, build, hair, size):
    try:
        gender_desc = AVATAR_GENDERS[gender]['desc']
        race_desc = AVATAR_RACES[race]['name'].split('/')[0]
        build_desc = AVATAR_BUILDS[build]['desc']
        size_desc = AVATAR_SIZES[size].get(gender, AVATAR_SIZES[size]['female'])
        
        if gender == "trans":
            prompt = f"Beautiful feminine {race_desc} trans woman, {build_desc}, {hair} hair, {size_desc}, nude, erotic pose, submissive, high quality"
        else:
            prompt = f"Beautiful {race_desc} {gender_desc}, {build_desc}, {hair} hair, {size_desc}, nude, erotic pose, submissive, high quality"
        
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {
            "model": "chroma",
            "prompt": prompt,
            "width": 512,
            "height": 768,
            "seed": random.randint(1, 1000000)
        }
        
        response = requests.post(VENICE_IMAGE_URL, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if 'images' in result and result['images']:
                return result['images'][0]
        
        return None
        
    except Exception as e:
        logger.error(f"Avatar error: {e}")
        return None

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
        yes_count = len(get_user_kinks(user, "yes"))
        okay_count = len(get_user_kinks(user, "okay"))
        
        await update.message.reply_text(
            f"Welcome back, {username}!\n\n"
            f"📍 Location: {loc}\n"
            f"Risk: {user.risk_level} | Points: {user.points}\n"
            f"Streak: {user.streak}\n"
            f"Kinks: {yes_count} desired, {okay_count} allowed\n\n"
            f"/task - Get challenge\n"
            f"/wherenow - Set location\n"
            f"/outfit - Set clothing\n"
            f"/avatar - Create avatar\n"
            f"/risk - Set risk\n"
            f"/kinks - Set kink preferences\n"
            f"/interval - Set auto-task interval\n"
            f"/schedule - Auto-tasks on/off\n"
            f"/status - Check task\n"
            f"/rewards - Check reward progress"
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
            await query.edit_message_text("Describe your outfit:")
            return
        
        outfit = OUTFIT_OPTIONS[outfit_key]
        items = outfit.get(f"{user.gender}_items", outfit["male_items"])
        user.current_outfit = outfit["name"]
        user.outfit_items = json.dumps(items)
        session.commit()
        
        await query.edit_message_text(f"{outfit['emoji']} Outfit: {outfit['name']}\n\nUse /wherenow to set location!")
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
            await update.message.reply_text("✅ Outfit saved. Use /wherenow!")
    finally:
        session.close()
    
    context.user_data['awaiting_custom_outfit'] = False

async def wherenow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏪 Store", callback_data="ctx_store")],
        [InlineKeyboardButton("🏠 Home", callback_data="ctx_home")],
        [InlineKeyboardButton("🏨 Hotel", callback_data="ctx_hotel")],
        [InlineKeyboardButton("🚗 Vehicle", callback_data="ctx_car")],
        [InlineKeyboardButton("🏢 Work", callback_data="ctx_work")],
        [InlineKeyboardButton("✏️ Custom", callback_data="ctx_custom")]
    ]
    await update.message.reply_text("📍 Where are you?", reply_markup=InlineKeyboardMarkup(keyboard))

async def context_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    ctx_type = query.data.replace("ctx_", "")
    
    if ctx_type == "custom":
        context.user_data['awaiting_custom_location'] = True
        await query.edit_message_text("Describe exactly where you are:")
        return
    
    loc_map = {"store": "Retail Store", "home": "Home", "hotel": "Hotel", "car": "Vehicle", "work": "Work"}
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
    
    keyboard = [
        [InlineKeyboardButton("🧍 Alone", callback_data="present_alone")],
        [InlineKeyboardButton("💑 Partner", callback_data="present_partner")],
        [InlineKeyboardButton("🏠 Roommates", callback_data="present_roommates")],
        [InlineKeyboardButton("👨‍👩‍👧 Family", callback_data="present_parents")],
        [InlineKeyboardButton("👶 Kids", callback_data="present_kids")],
        [InlineKeyboardButton("👥 Public", callback_data="present_public")]
    ]
    await query.edit_message_text(f"📍 {location}\n\nWho is present?", reply_markup=InlineKeyboardMarkup(keyboard))

async def present_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    present_type = query.data.replace("present_", "")
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.context_others = present_type
            user.context_alone = (present_type == "alone")
            if present_type == "kids" and user.risk_level > 2:
                user.risk_level = 2
            session.commit()
    finally:
        session.close()
    
    keyboard = [
        [InlineKeyboardButton("🔒 Private", callback_data="privacy_private")],
        [InlineKeyboardButton("🚪 Semi-private", callback_data="privacy_semi")],
        [InlineKeyboardButton("👁️ Exposed", callback_data="privacy_exposed")],
        [InlineKeyboardButton("🌍 Public", callback_data="privacy_public")]
    ]
    ctx_name = CONTEXT_OPTIONS.get(present_type, {}).get("name", present_type)
    await query.edit_message_text(f"👥 {ctx_name}\n\nPrivacy level?", reply_markup=InlineKeyboardMarkup(keyboard))

async def privacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    privacy = query.data.replace("privacy_", "")
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.context_privacy = privacy
            session.commit()
            await query.edit_message_text(f"✅ Context set!\n\nUse /kinks to set your preferences, then /task for challenges!")
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
                [InlineKeyboardButton("👥 Public", callback_data="present_public")]
            ]
            await update.message.reply_text(f"📍 {location}\n\nWho is present?", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()
    
    context.user_data['awaiting_custom_location'] = False

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(f"{i}️⃣ {RISK_LEVELS[i]['name']}", callback_data=f"risk_{i}")] for i in range(1, 6)]
    await update.message.reply_text("Select risk:", reply_markup=InlineKeyboardMarkup(keyboard))

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
            await query.edit_message_text(f"Risk: {RISK_LEVELS[risk]['name']}")
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
        for kink_key, (name, desc) in KINK_CATEGORIES.items():
            current_level = getattr(user, kink_key, "no")
            emoji = KINK_LEVELS[current_level]["emoji"]
            keyboard.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"kinkmenu_{kink_key}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Done", callback_data="kinks_done")])
        
        await update.message.reply_text(
            "🎭 Kink Preferences\n\n"
            "❌ = No (hard limit)\n"
            "⭕ = Okay (Dom may use)\n"
            "✅ = Yes (desired/favorite)\n\n"
            "Tap a kink to cycle through options:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def kink_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    kink_key = query.data.replace("kinkmenu_", "")
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        
        current = getattr(user, kink_key, "no")
        name = KINK_CATEGORIES[kink_key][0]
        desc = KINK_CATEGORIES[kink_key][1]
        
        keyboard = [
            [InlineKeyboardButton(f"{'✅' if current == 'no' else ''} ❌ No (Never)", callback_data=f"kinkset_{kink_key}_no")],
            [InlineKeyboardButton(f"{'✅' if current == 'okay' else ''} ⭕ Okay (Dom decides)", callback_data=f"kinkset_{kink_key}_okay")],
            [InlineKeyboardButton(f"{'✅' if current == 'yes' else ''} ✅ Yes (Desired!)", callback_data=f"kinkset_{kink_key}_yes")],
            [InlineKeyboardButton("🔙 Back", callback_data="kinks_back")]
        ]
        
        await query.edit_message_text(
            f"{name}\n\n{desc}\n\nCurrent: {KINK_LEVELS[current]['emoji']} {KINK_LEVELS[current]['name']}\n\nSelect new level:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def kink_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace("kinkset_", "").rsplit("_", 1)
    kink_key = data[0]
    level = data[1]
    user_id = update.effective_user.id
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user and hasattr(user, kink_key):
            setattr(user, kink_key, level)
            session.commit()
            
            name = KINK_CATEGORIES[kink_key][0]
            await query.edit_message_text(
                f"✅ {name} set to {KINK_LEVELS[level]['emoji']} {KINK_LEVELS[level]['name']}"
            )
            
            await asyncio.sleep(0.5)
            await kinks_back_callback(update, context)
    finally:
        session.close()

async def kinks_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await query.edit_message_text("Use /start first")
            return
        
        keyboard = []
        for kink_key, (name, desc) in KINK_CATEGORIES.items():
            current_level = getattr(user, kink_key, "no")
            emoji = KINK_LEVELS[current_level]["emoji"]
            keyboard.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"kinkmenu_{kink_key}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Done", callback_data="kinks_done")])
        
        await query.edit_message_text(
            "🎭 Kink Preferences\n\n"
            "❌ = No (hard limit)\n"
            "⭕ = Okay (Dom may use)\n"
            "✅ = Yes (desired/favorite)\n\n"
            "Tap a kink to cycle through options:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def kinks_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Kinks updated! Use /task to get challenges.")

async def interval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        current_min = user.min_interval
        current_max = user.max_interval
        
        await update.message.reply_text(
            f"⏱️ Auto-Task Interval\n\n"
            f"Current: {current_min}-{current_max} minutes\n\n"
            f"Send new interval as: MIN MAX\n"
            f"Examples: '30 60' or '60 120'\n\n"
            f"Send 'cancel' to keep current."
        )
        context.user_data['awaiting_interval'] = True
    finally:
        session.close()

async def handle_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_interval'):
        return
    
    text = update.message.text.strip().lower()
    
    if text == 'cancel':
        await update.message.reply_text("Interval unchanged.")
        context.user_data['awaiting_interval'] = False
        return
    
    try:
        parts = text.split()
        if len(parts) != 2:
            raise ValueError("Need 2 numbers")
        
        min_int = int(parts[0])
        max_int = int(parts[1])
        
        if min_int < 5 or max_int > 1440 or min_int >= max_int:
            await update.message.reply_text("❌ Invalid range. Min 5-1440, max > min.")
            return
        
        user_id = update.effective_user.id
        session = get_session()
        try:
            user = session.query(UserState).filter_by(user_id=user_id).first()
            if user:
                user.min_interval = min_int
                user.max_interval = max_int
                session.commit()
                await update.message.reply_text(f"✅ Interval: {min_int}-{max_int} minutes")
        finally:
            session.close()
            
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Send as: MIN MAX")
        return
    
    context.user_data['awaiting_interval'] = False

# ============ CHAT HANDLER ============
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to regular messages conversationally"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Skip if waiting for custom input
    if context.user_data.get('awaiting_custom_outfit') or \
       context.user_data.get('awaiting_custom_location') or \
       context.user_data.get('awaiting_interval'):
        return
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        title = get_title(user.avatar_gender if user else None)
        
        context_info = ""
        if user:
            context_info = f"User is {user.gender or 'unknown'}, wearing {user.current_outfit or 'unknown'}, at {user.custom_location or 'unknown'}. "
            context_info += f"They have {user.points} points, streak {user.streak}. "
        
        prompt = f"""You are a dominant {title}. Respond to this message from your submissive briefly (1-2 sentences). Be playful but commanding, use pet names.

{context_info}

Their message: "{message_text}"

Respond as {title}:"""
        
        response = await generate_ai_response(prompt, temperature=0.9)
        
        if response:
            await update.message.reply_text(response.strip())
        else:
            fallbacks = [
                f"Mmm? Speak up, pet.",
                f"Is that how you address {title}?",
                f"You're distracting me, toy.",
                f"Save your words and show me action instead.",
                f"Interesting. Now get back to your task."
            ]
            await update.message.reply_text(random.choice(fallbacks))
            
    finally:
        session.close()

# ============ TASK COMMANDS ============
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
            await update.message.reply_text(f"You have a task pending! {max(0, time_left):.0f} minutes left.")
            return
        
        await update.message.reply_text("Generating your task...")
        
        # Avatar image chance
        if random.random() < 0.3 and user.avatar_gender:
            avatar_url = await generate_avatar_pose(user, "dominant")
            if avatar_url:
                await context.bot.send_photo(chat_id=user_id, photo=avatar_url, caption="Your task awaits...")
                await asyncio.sleep(1)
        
        task_text = await generate_task_text(user, session)
        
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=30)
        
        task = Task(user_id=user_id, task_text=task_text, risk_level=user.risk_level, created_at=now, expires_at=expires)
        session.add(task)
        session.commit()
        
        scheduler.add_job(
            auto_clear_task,
            'date',
            run_date=expires,
            args=[user_id, task.id, context],
            id=f"timeout_{task.id}",
            replace_existing=True
        )
        
        title = get_title(user.avatar_gender)
        
        keyboard = [
            [InlineKeyboardButton(f"📸 Done, {title}", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("❌ I can't...", callback_data=f"giveup_{task.id}")]
        ]
        
        await update.message.reply_text(
            f"🎯 TASK\n\n{task_text}\n\n30 minutes.",
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
            
            title = get_title(user.avatar_gender)
            keyboard = [
                [InlineKeyboardButton(f"📸 Done, {title}", callback_data=f"complete_{active.id}")],
                [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{active.id}")]
            ]
            await update.message.reply_text(
                f"⏰ {max(0, time_left):.0f} min left\n\n{active.task_text[:200]}...",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            loc = user.custom_location or user.location or "Not set"
            interval = f"{user.min_interval}-{user.max_interval} min" if user.scheduling_enabled else "Off"
            yes_kinks = len(get_user_kinks(user, "yes"))
            okay_kinks = len(get_user_kinks(user, "okay"))
            await update.message.reply_text(
                f"No active task.\n\n"
                f"📍 {loc} | Points: {user.points} | Streak: {user.streak}\n"
                f"Kinks: {yes_kinks} desired, {okay_kinks} allowed\n"
                f"Auto: {interval}\n\n"
                f"Use /task!"
            )
    finally:
        session.close()

async def rewards_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        await update.message.reply_text(
            f"🎁 Rewards unlock every 5-10 tasks completed.\n\n"
            f"Current streak: {user.streak}\n"
            f"Total completed: {user.completed_tasks}\n\n"
            f"Keep completing tasks to earn avatar rewards!"
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
            await update.message.reply_text("Task expired. Use /task.")
            return
        
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        await update.message.reply_text("Checking your photo...")
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
            user.challenges_since_reward += 1
            session.commit()
            
            title = get_title(user.avatar_gender)
            
            # Check for reward (every 5-10 challenges)
            if user.challenges_since_reward >= random.randint(5, 10):
                user.challenges_since_reward = 0
                session.commit()
                
                await update.message.reply_text(f"✅ +{10 * task.risk_level} points! Streak: {user.streak}\n\n🎁 Reward earned!")
                
                reward_url = await generate_avatar_pose(user, "reward")
                if reward_url:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=reward_url,
                        caption=f"🎁 Your reward, {title} is pleased."
                    )
                else:
                    await update.message.reply_text("🎁 Reward earned!")
            else:
                await update.message.reply_text(f"✅ +{10 * task.risk_level} points! Streak: {user.streak}")
        else:
            if task.verification_attempts >= 2:
                task.status = "failed"
                user = session.query(UserState).filter_by(user_id=user_id).first()
                user.consecutive_failures += 1
                session.commit()
                await update.message.reply_text(f"❌ Failed: {reason}")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔄 Try Again", callback_data=f"retry_{task.id}")],
                    [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
                ]
                await update.message.reply_text(f"❌ {reason}\n\n1 try left.", reply_markup=InlineKeyboardMarkup(keyboard))
        
        session.commit()
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await update.message.reply_text("Error processing photo.")
    finally:
        session.close()

async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Send photo proof.")

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
            await query.edit_message_text("❌ Task abandoned. -5 points.")
    finally:
        session.close()

async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Send retry photo.")

async def auto_clear_task(user_id, task_id, context):
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
                await context.bot.send_message(chat_id=user_id, text="⏰ Task expired. -10 points.")
            except Exception as e:
                logger.error(f"Notify error: {e}")
        session.commit()
    except Exception as e:
        logger.error(f"Auto-clear error: {e}")
    finally:
        session.close()

# ============ AVATAR COMMANDS ============
async def avatar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        keyboard = [
            [InlineKeyboardButton(f"{g['emoji']} {g['name']}", callback_data=f"av_gender_{k}")]
            for k, g in AVATAR_GENDERS.items()
        ]
        await update.message.reply_text("🎨 Create Your Avatar\n\nStep 1/5: Select gender:", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

async def avatar_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("av_gender_", "")
    context.user_data['avatar_gender'] = gender
    
    keyboard = [
        [InlineKeyboardButton(f"{r['emoji']} {r['name']}", callback_data=f"av_race_{k}")]
        for k, r in AVATAR_RACES.items()
    ]
    await query.edit_message_text(f"✅ Gender: {AVATAR_GENDERS[gender]['name']}\n\nStep 2/5: Select race:", reply_markup=InlineKeyboardMarkup(keyboard))

async def avatar_race_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    race = query.data.replace("av_race_", "")
    context.user_data['avatar_race'] = race
    
    keyboard = [
        [InlineKeyboardButton(f"{b['emoji']} {b['name']}", callback_data=f"av_build_{k}")]
        for k, b in AVATAR_BUILDS.items()
    ]
    await query.edit_message_text(f"✅ Race: {AVATAR_RACES[race]['name']}\n\nStep 3/5: Select build:", reply_markup=InlineKeyboardMarkup(keyboard))

async def avatar_build_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    build = query.data.replace("av_build_", "")
    context.user_data['avatar_build'] = build
    
    keyboard = [[InlineKeyboardButton(h, callback_data=f"av_hair_{k}")] for k, h in AVATAR_HAIR.items()]
    await query.edit_message_text(f"✅ Build: {AVATAR_BUILDS[build]['name']}\n\nStep 4/5: Select hair:", reply_markup=InlineKeyboardMarkup(keyboard))

async def avatar_hair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    hair = query.data.replace("av_hair_", "")
    context.user_data['avatar_hair'] = hair
    
    gender = context.user_data.get('avatar_gender', 'female')
    keyboard = [[InlineKeyboardButton(f"{s['emoji']} {s['name']}", callback_data=f"av_size_{k}")] for k, s in AVATAR_SIZES.items()]
    
    size_label = "breast" if gender == "female" else "genital"
    if gender == "trans":
        size_label = "breast and penis"
    
    await query.edit_message_text(f"✅ Hair: {AVATAR_HAIR[hair]}\n\nStep 5/5: Select {size_label} size:", reply_markup=InlineKeyboardMarkup(keyboard))

async def avatar_size_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    size = query.data.replace("av_size_", "")
    
    user_id = update.effective_user.id
    gender = context.user_data.get('avatar_gender')
    race = context.user_data.get('avatar_race')
    build = context.user_data.get('avatar_build')
    hair = context.user_data.get('avatar_hair')
    
    await query.edit_message_text("🎨 Generating avatar...")
    
    image_url = await generate_avatar_pose_image(gender, race, build, hair, size)
    
    if image_url:
        session = get_session()
        try:
            user = session.query(UserState).filter_by(user_id=user_id).first()
            if user:
                user.avatar_gender = gender
                user.avatar_race = race
                user.avatar_build = build
                user.avatar_hair = hair
                user.avatar_genital_size = size
                session.commit()
            
            avatar = AvatarImage(user_id=user_id, image_url=image_url, gender=gender, race=race, build=build)
            session.add(avatar)
            session.commit()
            
            await query.edit_message_text("✅ Avatar generated!")
            await context.bot.send_photo(
                chat_id=user_id,
                photo=image_url,
                caption=f"🎨 Your Avatar\nGender: {AVATAR_GENDERS[gender]['name']}\nRace: {AVATAR_RACES[race]['name']}\nBuild: {AVATAR_BUILDS[build]['name']}\nHair: {AVATAR_HAIR[hair]}\nSize: {AVATAR_SIZES[size]['name']}"
            )
        finally:
            session.close()
    else:
        await query.edit_message_text("❌ Error generating avatar.")

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
            await query.edit_message_text(f"✅ Auto-tasks enabled!")
        elif query.data == "sched_disable":
            user.scheduling_enabled = False
            user.next_task_time = None
            session.commit()
            await query.edit_message_text("⏹️ Auto-tasks disabled.")
    finally:
        session.close()

async def random_interval_check(context):
    session = get_session()
    try:
        now = datetime.now(timezone.utc)
        users = session.query(UserState).filter(UserState.scheduling_enabled == True, UserState.next_task_time <= now).all()
        
        for user in users:
            active = session.query(Task).filter_by(user_id=user.user_id, status="pending").first()
            if not active:
                try:
                    if random.random() < 0.3 and user.avatar_gender:
                        avatar_url = await generate_avatar_pose(user, "dominant")
                        if avatar_url:
                            await context.bot.send_photo(chat_id=user.user_id, photo=avatar_url, caption="Your task awaits...")
                            await asyncio.sleep(1)
                    
                    task_text = await generate_task_text(user, session)
                    
                    expires = now + timedelta(minutes=30)
                    task = Task(user_id=user.user_id, task_text=task_text, risk_level=user.risk_level, created_at=now, expires_at=expires)
                    session.add(task)
                    session.commit()
                    
                    title = get_title(user.avatar_gender)
                    
                    scheduler.add_job(
                        auto_clear_task,
                        'date',
                        run_date=expires,
                        args=[user.user_id, task.id, context],
                        id=f"timeout_{task.id}",
                        replace_existing=True
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton(f"📸 Done, {title}", callback_data=f"complete_{task.id}")],
                        [InlineKeyboardButton("❌ I can't...", callback_data=f"giveup_{task.id}")]
                    ]
                    await context.bot.send_message(
                        chat_id=user.user_id,
                        text=f"🎯 AUTO TASK\n\n{task_text}\n\n30 minutes.",
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

# ============ RESET ============
async def resetowner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚠️ YES DELETE ALL", callback_data="reset_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="reset_cancel")]
    ]
    await update.message.reply_text("⚠️ DELETE ALL DATA?", reply_markup=InlineKeyboardMarkup(keyboard))

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
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # FIX: Use application.job_queue instead of apscheduler directly
    # Or wrap the call properly
    
    async def scheduled_check(context: ContextTypes.DEFAULT_TYPE):
        await random_interval_check(context.application)
    
    # Add to job_queue instead of using apscheduler directly
    application.job_queue.run_repeating(
        scheduled_check,
        interval=60,  # 60 seconds
        first=10,  # Start after 10 seconds
        name="interval_check"
    )
        
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
    application.add_handler(CommandHandler("interval", interval_cmd))
    application.add_handler(CommandHandler("avatar", avatar_cmd))
    application.add_handler(CommandHandler("resetowner", resetowner_cmd))
    application.add_handler(CommandHandler("rewards", rewards_cmd))
    application.add_handler(CommandHandler("help", start))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    application.add_handler(CallbackQueryHandler(outfit_callback, pattern="^outfit_"))
    application.add_handler(CallbackQueryHandler(context_callback, pattern="^ctx_"))
    application.add_handler(CallbackQueryHandler(present_callback, pattern="^present_"))
    application.add_handler(CallbackQueryHandler(privacy_callback, pattern="^privacy_"))
    application.add_handler(CallbackQueryHandler(risk_callback, pattern="^risk_"))
    application.add_handler(CallbackQueryHandler(kink_menu_callback, pattern="^kinkmenu_"))
    application.add_handler(CallbackQueryHandler(kink_set_callback, pattern="^kinkset_"))
    application.add_handler(CallbackQueryHandler(kinks_back_callback, pattern="^kinks_back"))
    application.add_handler(CallbackQueryHandler(kinks_done_callback, pattern="^kinks_done"))
    application.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_"))
    application.add_handler(CallbackQueryHandler(giveup_callback, pattern="^giveup_"))
    application.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(schedule_callback, pattern="^sched_"))
    application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    application.add_handler(CallbackQueryHandler(avatar_gender_callback, pattern="^av_gender_"))
    application.add_handler(CallbackQueryHandler(avatar_race_callback, pattern="^av_race_"))
    application.add_handler(CallbackQueryHandler(avatar_build_callback, pattern="^av_build_"))
    application.add_handler(CallbackQueryHandler(avatar_hair_callback, pattern="^av_hair_"))
    application.add_handler(CallbackQueryHandler(avatar_size_callback, pattern="^av_size_"))
    
    # Messages
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Custom text handlers
    async def custom_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('awaiting_custom_outfit'):
            await handle_custom_outfit(update, context)
        elif context.user_data.get('awaiting_custom_location'):
            await handle_custom_location(update, context)
        elif context.user_data.get('awaiting_interval'):
            await handle_interval_input(update, context)
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_text_handler))
    
    # General chat handler (must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()