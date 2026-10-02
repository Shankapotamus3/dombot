import os
import json
import logging
import asyncio
import base64
import random
import requests
import cloudinary
import cloudinary.uploader
from io import BytesIO
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, DateTime, Boolean, Text, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ============ CONFIG ============
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
VENICE_API_KEY = os.getenv('VENICE_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
VENICE_API_URL = "https://api.venice.ai/api/v1"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

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
    avatar_gender = Column(String(20), default=None)
    avatar_race = Column(String(20), default=None)
    avatar_build = Column(String(20), default=None)
    avatar_hair = Column(String(20), default=None)
    avatar_genital_size = Column(String(20), default=None)
    challenges_since_reward = Column(Integer, default=0)
    last_kinks_used = Column(Text, default=None)
    awaiting_custom_outfit = Column(Boolean, default=False)
    awaiting_custom_location = Column(Boolean, default=False)
    awaiting_interval = Column(Boolean, default=False)
    # New columns for periodic avatars
    last_avatar_sent_at = Column(DateTime(timezone=True), nullable=True)
    avatar_interval_minutes = Column(Integer, default=60)  # How often to send avatars
    avatar_enabled = Column(Boolean, default=True)
    # Kink columns
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
    cloudinary_url = Column(Text, nullable=True)
    cloudinary_public_id = Column(Text, nullable=True)
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
    cloudinary_url = Column(Text, nullable=True)
    cloudinary_public_id = Column(Text, nullable=True)
    gender = Column(String(20))
    race = Column(String(20))
    build = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class UserImage(Base):
    __tablename__ = 'user_images'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    telegram_file_id = Column(Text, nullable=False)
    cloudinary_url = Column(Text, nullable=True)
    cloudinary_public_id = Column(Text, nullable=True)
    image_type = Column(String(50), default='user_upload')
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# ============ CLOUDINARY HELPERS ============
async def upload_to_cloudinary(image_bytes, user_id, image_type='user_upload', folder='telegram_bot'):
    try:
        if isinstance(image_bytes, (bytes, bytearray)):
            image_bytes = BytesIO(image_bytes)
        image_bytes.seek(0)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        public_id = f"{folder}/user_{user_id}/{image_type}_{timestamp}_{random.randint(1000, 9999)}"
        result = cloudinary.uploader.upload(
            image_bytes,
            public_id=public_id,
            resource_type="image",
            context={'user_id': str(user_id), 'image_type': image_type, 'uploaded_at': str(datetime.now(timezone.utc))},
            tags=[f"user_{user_id}", image_type, "telegram_bot"]
        )
        logger.info(f"Cloudinary upload success: {result.get('public_id')}")
        return {'url': result.get('secure_url'), 'public_id': result.get('public_id'), 'width': result.get('width'), 'height': result.get('height')}
    except Exception as e:
        logger.error(f"Cloudinary upload error: {e}")
        return None

# ============ CONSTANTS ============
RISK_LEVELS = {
    1: {"name": "Safe", "description": "Private, no exposure, completely controlled environment"},
    2: {"name": "Low", "description": "Private with minor vulnerability (unlocked door, thin walls)"},
    3: {"name": "Medium", "description": "Semi-private (near windows, balcony, could be heard/seen)"},
    4: {"name": "High", "description": "Semi-public (visible areas, shared spaces, immediate exposure risk)"},
    5: {"name": "Extreme", "description": "Public-adjacent (hallways, stairwells, high exposure possible)"}
}

RISK_INSPIRATION = {
    "Hotel": {3: ["room with curtains open", "balcony", "near window"], 4: ["room doorway", "connecting door area", "bathroom with door cracked"], 5: ["hallway", "stairwell", "elevator lobby", "ice machine room"]},
    "Home": {3: ["bedroom with door open", "near window", "garage"], 4: ["front porch", "backyard", "garage with door open", "living room"], 5: ["driveway", "apartment hallway", "shared laundry room"]},
    "Retail Store": {3: ["dressing room", "back corner"], 4: ["fitting room with curtain", "employee hallway"], 5: ["parking lot", "loading dock", "alley behind store"]},
    "Vehicle": {3: ["parked in empty lot", "back seat"], 4: ["parked near others", "rest stop"], 5: ["busy parking lot", "gas station", "highway rest area"]},
    "Work": {3: ["private office", "bathroom stall"], 4: ["empty conference room", "stairwell"], 5: ["parking garage", "rooftop", "elevator"]}
}

def get_risk_inspiration(location, risk_level):
    if risk_level < 3:
        return ""
    location_key = None
    location_lower = (location or "").lower()
    for key in RISK_INSPIRATION:
        if key.lower() in location_lower:
            location_key = key
            break
    if not location_key:
        location_key = "Home"
    examples = RISK_INSPIRATION.get(location_key, {}).get(risk_level, [])
    if examples:
        return f" (inspiration: {', '.join(examples[:2])})"
    return ""

KINK_CATEGORIES = {
    "kink_exposure": ("📸 Exposure", "Being seen/photographed"),
    "kink_humiliation": ("😳 Humiliation", "Verbal degradation"),
    "kink_degradation": ("🗑️ Degradation", "Being treated as inferior"),
    "kink_bondage": ("⛓️ Bondage", "Restraint"),
    "kink_pain": ("🔥 Pain", "Impact play"),
    "kink_service": ("🙇 Service", "Serving, chores"),
    "kink_edging": ("⏱️ Edging", "Orgasm denial"),
    "kink_watersports": ("💧 Watersports", "Pee play"),
    "kink_exhibitionism": ("🎭 Exhibitionism", "Public exposure"),
    "kink_roleplay": ("🎪 Roleplay", "Scenarios"),
    "kink_petplay": ("🐾 Pet Play", "Animal roleplay"),
    "kink_feminization": ("💄 Feminization", "Forced fem"),
    "kink_cbt": ("🔩 CBT", "Cock/ball torture"),
    "kink_breathplay": ("😮‍💨 Breath Play", "Choking"),
    "kink_sensory": ("🙈 Sensory", "Blindfolds"),
    "kink_temperature": ("🌡️ Temperature", "Ice/heat/wax"),
    "kink_marking": ("✏️ Marking", "Body writing"),
    "kink_spanking": ("👋 Spanking", "Slapping"),
    "kink_nipple": ("👀 Nipple", "Nipple play"),
    "kink_anal": ("🍑 Anal", "Ass play"),
    "kink_gags": ("🔇 Gags", "Mouth restriction"),
    "kink_social_media": ("📱 Social Media", "Online exposure")
}

KINK_LEVELS = {"no": {"emoji": "❌", "name": "No", "desc": "Hard limit"}, "okay": {"emoji": "⭕", "name": "Okay", "desc": "Allowed"}, "yes": {"emoji": "✅", "name": "Yes", "desc": "Desired"}}

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

AVATAR_GENDERS = {"male": {"emoji": "👨", "name": "Male", "desc": "Masculine, muscular or slim"}, "female": {"emoji": "👩", "name": "Female", "desc": "Feminine, curvy or slim"}, "trans": {"emoji": "⚧", "name": "Trans/Futa", "desc": "Feminine with penis and breasts"}}
AVATAR_RACES = {"white": {"emoji": "🏻", "name": "White/Caucasian"}, "black": {"emoji": "🏿", "name": "Black/African"}, "asian": {"emoji": "🌸", "name": "Asian"}, "hispanic": {"emoji": "🌶️", "name": "Hispanic/Latino"}, "middle_eastern": {"emoji": "🕌", "name": "Middle Eastern"}, "indian": {"emoji": "🪷", "name": "Indian/South Asian"}}
AVATAR_BUILDS = {"slim": {"emoji": "🧍", "name": "Slim", "desc": "extremely skinny, petite, waif-like"}, "athletic": {"emoji": "💪", "name": "Athletic", "desc": "fit, toned, muscular"}, "curvy": {"emoji": "🍑", "name": "Curvy", "desc": "full figured, wide hips"}, "muscular": {"emoji": "🏋️", "name": "Muscular", "desc": "ripped, bodybuilder"}}
AVATAR_HAIR = {"blonde": "Blonde", "brunette": "Brunette", "black": "Black", "red": "Red", "pink": "Pink", "blue": "Blue", "purple": "Purple", "white": "White/Silver"}
AVATAR_SIZES = {"small": {"emoji": "🔹", "name": "Small", "male": "small penis", "female": "small breasts", "trans": "small breasts and penis"}, "medium": {"emoji": "🔸", "name": "Medium", "male": "medium penis", "female": "medium breasts", "trans": "medium breasts and penis"}, "large": {"emoji": "🔶", "name": "Large", "male": "large penis", "female": "large breasts", "trans": "large breasts and penis"}}

DOMINANT_POSES = ["standing with hands on hips, dominant stance", "sitting on throne-like chair, legs spread, commanding", "holding riding crop, stern expression", "crossed arms, looking down at camera, powerful", "holding leash, dominant posture", "standing over camera angle, feet visible, superior pose", "holding whip behind back, confident stance", "one foot on chair, elbow on knee, dominant", "finger pointing down, commanding gesture", "holding collar and leash, expectant expression"]
DOMINANT_OUTFITS = ["latex catsuit", "leather corset and thigh boots", "dominatrix outfit with gloves", "sheer bodysuit with harness", "pvc dress with choker", "fishnet bodysuit with straps", "leather harness and panties", "lace lingerie with garter belt", "shiny metallic bikini", "strappy harness outfit"]

# Greeting keywords
GREETINGS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy", "greetings", "sup", "yo"]
TASK_INQUIRIES = ["task", "my task", "current task", "what task", "do i have a task", "any task", "status", "check task", "pending task"]
COMPLIMENTS = ["beautiful", "sexy", "hot", "gorgeous", "pretty", "cute", "amazing", "perfect", "wonderful", "great", "good", "love", "like you", "miss you"]
DISRESPECTFUL = ["fuck", "shit", "bitch", "stupid", "dumb", "hate", "suck", "ass", "idiot", "moron"]

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

def get_title(avatar_gender):
    return "Sir" if avatar_gender == "male" else "Mistress"

async def generate_ai_response(prompt, temperature=0.9):
    try:
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "claude-opus-4-8-fast", "messages": [{"role": "system", "content": "You are a playful but demanding Domme. Speak with confidence, occasional teasing, and personality. Be conversational, use pet names, mix encouragement with demands."}, {"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": 500}
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
        prompt = f"""Task: {task_desc}\n\nVerify this photo. Be REASONABLE about:\n- Selfie angles (can't see own face/back in selfie)\n- Lighting and shadows  \n- Equivalent items (any clamp = clothespin, any tie = rope, etc.)\n\nDoes this show completion? Reply:\nVERIFIED: yes/no\nREASON: brief\n\nBe lenient - if effort was made, verify yes."""
        data = {"model": "claude-opus-4-8-fast", "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}], "max_tokens": 200}
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
    outfit_items = json.loads(user.outfit_items or '[]')
    gender = user.gender or "nonbinary"
    max_risk = user.risk_level or 1
    location = user.custom_location or user.location or "Unknown"
    others = user.context_others or "alone"
    privacy = user.context_privacy or "private"
    actual_risk = random.randint(1, max_risk)
    if others == "kids":
        actual_risk = min(2, actual_risk)
        max_risk = min(2, max_risk)
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
    risk_desc = RISK_LEVELS[actual_risk]["description"]
    risk_inspiration = get_risk_inspiration(location, actual_risk) if actual_risk >= 3 else ""
    yes_text = f"\nDESIRED: {', '.join(yes_kinks)}" if yes_kinks else ""
    selected_text = f"\nUSE: {', '.join(selected_kinks)}"
    forbidden_text = f"\n\nNEVER: {', '.join(forbidden_kinks)}" if forbidden_kinks else ""
    prompt = f"""Create ONE BDSM task for a {gender} sub.\n\nLocation: {location}\nContext: {others}, {privacy} privacy\nMax Risk Level: {max_risk}/5 (user allows up to this level)\nThis Task Risk: {actual_risk}/5 - {risk_desc}{risk_inspiration}\nOutfit: {user.current_outfit}\nItems: {items_text}\nBody parts: {body_parts}{yes_text}{selected_text}{forbidden_text}\n\nRules:\n- Single action, photo proof required\n- No time durations\n- Never use forbidden kinks\n- Be creative and unpredictable\n- Risk 3-5: Consider windows, doorways, visibility, shared spaces\n- Risk 4-5: Can include immediate exterior areas, hallways, stairwells\n- Use the risk level as creative inspiration, not a requirement\n- Vary the intensity - sometimes mild, sometimes pushing boundaries\n\nTask:"""
    response = await generate_ai_response(prompt, temperature=0.95)
    if response:
        response = response.strip()
        forbidden_keywords = {"marking": ["write", "marker", "sharpie", "draw on", "body writing", "written", "label"], "watersports": ["pee", "piss", "urine", "wet yourself"], "breathplay": ["choke", "strangle", "suffocate"], "social_media": ["post", "upload", "instagram", "twitter", "facebook", "share online"]}
        for forbidden_kink, keywords in forbidden_keywords.items():
            if forbidden_kink in forbidden_kinks:
                if any(kw in response.lower() for kw in keywords):
                    logger.warning(f"Filtered forbidden kink '{forbidden_kink}'")
                    return await generate_task_text(user, session)
        return response
    fallbacks = {1: f"Strip completely at {location} and photograph your reflection", 2: f"Strip at {location} near the unlocked door and take a photo", 3: f"Expose yourself at {location} near a window and photograph the view", 4: f"Step just outside {location} doorway, expose yourself, and take a photo", 5: f"Walk to the end of the {location} hallway, expose yourself briefly, photograph the empty hall behind you"}
    return fallbacks.get(actual_risk, fallbacks[1])

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
        data = {"model": "chroma", "prompt": prompt, "width": 512, "height": 768, "seed": random.randint(1, 1000000)}
        logger.info(f"Generating image with prompt: {prompt[:100]}...")
        response = requests.post(VENICE_IMAGE_URL, headers=headers, json=data, timeout=60)
        logger.info(f"Image API status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Response keys: {result.keys()}")
            if 'images' in result and result['images']:
                image_data = result['images'][0]
                logger.info(f"Image data type: {type(image_data)}, starts with: {str(image_data)[:50]}")
                if isinstance(image_data, str) and image_data.startswith('http'):
                    img_response = requests.get(image_data, timeout=30)
                    if img_response.status_code == 200:
                        logger.info(f"Downloaded image from URL: {len(img_response.content)} bytes")
                        return img_response.content
                    else:
                        logger.error(f"Failed to download: {img_response.status_code}")
                        return None
                elif isinstance(image_data, str) and image_data.startswith('data:image'):
                    base64_data = image_data.split(',')[1]
                    decoded = base64.b64decode(base64_data)
                    logger.info(f"Decoded base64 data URI: {len(decoded)} bytes")
                    return decoded
                elif isinstance(image_data, str):
                    try:
                        decoded = base64.b64decode(image_data)
                        logger.info(f"Decoded raw base64: {len(decoded)} bytes")
                        return decoded
                    except Exception as e:
                        logger.error(f"Failed to decode base64: {e}")
                        return None
                elif isinstance(image_data, bytes):
                    logger.info(f"Got bytes directly: {len(image_data)} bytes")
                    return image_data
        logger.error(f"Image API error: {response.status_code} - {response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Avatar error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

async def send_avatar_photo(context, chat_id, image_bytes, caption):
    try:
        if not image_bytes or len(image_bytes) < 1000:
            logger.error(f"Invalid image bytes: {len(image_bytes) if image_bytes else 'None'}")
            return False
        header = image_bytes[:20]
        is_jpeg = header.startswith(b'\xff\xd8')
        is_png = header.startswith(b'\x89PNG')
        if not (is_jpeg or is_png):
            logger.error(f"Invalid image format. Header: {header[:10]}")
            return False
        buf = BytesIO(image_bytes)
        buf.seek(0)
        await context.bot.send_photo(chat_id=chat_id, photo=buf, caption=caption)
        logger.info(f"Photo sent successfully: {len(image_bytes)} bytes")
        return True
    except Exception as e:
        logger.error(f"Send photo error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    return False

# ============ CUSTOM INPUT DISPATCHER ============
async def custom_input_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatch to appropriate custom input handler based on database flags"""
    user_id = update.effective_user.id
    text = update.message.text[:50]
    
    logger.info(f"=== DISPATCHER triggered for user {user_id}, text='{text}' ===")
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        
        if not user:
            logger.info(f"DISPATCHER: No user found, calling chat_handler")
            await chat_handler(update, context)
            return
        
        logger.info(f"DISPATCHER: Flags - outfit={user.awaiting_custom_outfit}, location={user.awaiting_custom_location}, interval={user.awaiting_interval}")
        
        # Check which flag is set and dispatch accordingly
        if user.awaiting_custom_outfit:
            logger.info(f"DISPATCHER: Routing to handle_custom_outfit")
            await handle_custom_outfit(update, context)
            return
            
        elif user.awaiting_custom_location:
            logger.info(f"DISPATCHER: Routing to handle_custom_location")
            await handle_custom_location(update, context)
            return
            
        elif user.awaiting_interval:
            logger.info(f"DISPATCHER: Routing to handle_interval_input")
            await handle_interval_input(update, context)
            return
            
        # No flags set - call chat_handler for conversation
        logger.info(f"DISPATCHER: No flags set, calling chat_handler")
        await chat_handler(update, context)
        
    finally:
        session.close()

# ============ ENHANCED CHAT HANDLER ============
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to regular messages conversationally with personality"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    message_lower = message_text.lower()
    
    logger.info(f"CHAT_HANDLER: Processing message from {user_id}: '{message_text[:50]}'")
    
    # Get user data
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        
        if not user:
            title = "Mistress"
            context_info = "This is a new submissive who hasn't completed setup."
            has_task = False
        else:
            title = get_title(user.avatar_gender)
            has_task = session.query(Task).filter_by(user_id=user_id, status="pending").first() is not None
            
            context_info = f"""
User Profile:
- Name/Username: {user.username or 'Unknown'}
- Gender: {user.gender or 'unknown'}
- Current outfit: {user.current_outfit or 'unknown'}
- Location: {user.custom_location or user.location or 'unknown'}
- Points: {user.points}
- Streak: {user.streak}
- Risk level: {user.risk_level}/5
- Has active task: {'Yes' if has_task else 'No'}
- Tasks completed: {user.completed_tasks}
"""
        
        # Check for greetings
        is_greeting = any(greet in message_lower for greet in GREETINGS)
        
        # Check for task inquiries
        is_task_inquiry = any(inquiry in message_lower for inquiry in TASK_INQUIRIES)
        
        # Check for compliments
        is_compliment = any(comp in message_lower for comp in COMPLIMENTS)
        
        # Check for disrespect
        is_disrespectful = any(disp in message_lower for disp in DISRESPECTFUL)
        
        # Build appropriate prompt based on message type
        if is_greeting:
            prompt = f"""You are a dominant {title}. The user just greeted you. Respond playfully and commandingly. Tease them a little. Use a pet name. Keep it to 1-2 sentences. Be seductive and confident.

{context_info}

They said: "{message_text}"

Respond as {title}:"""
            
        elif is_task_inquiry:
            if has_task:
                prompt = f"""You are a dominant {title}. The user is asking about their task. Remind them they have a task pending and tell them to stop stalling and complete it. Be firm but playful. Use a pet name. 1-2 sentences.

{context_info}

They said: "{message_text}"

Respond as {title}:"""
            else:
                prompt = f"""You are a dominant {title}. The user is asking about a task but doesn't have one. Tell them to use /task to get one, or tease them about being eager. Be playful and commanding. Use a pet name. 1-2 sentences.

{context_info}

They said: "{message_text}"

Respond as {title}:"""
                
        elif is_compliment:
            prompt = f"""You are a dominant {title}. The user just complimented you. Accept it as your due, maybe tease them about trying to get on your good side. Be confident and slightly arrogant in a playful way. Use a pet name. 1-2 sentences.

{context_info}

They said: "{message_text}"

Respond as {title}:"""
            
        elif is_disrespectful:
            prompt = f"""You are a dominant {title}. The user was disrespectful. Put them in their place firmly. Threaten punishment or extra tasks. Be stern and commanding. Use harsh pet names. 1-2 sentences.

{context_info}

They said: "{message_text}"

Respond as {title}:"""
            
        else:
            # General conversation
            prompt = f"""You are a dominant {title} addressing your submissive. Be playful, teasing, and commanding. Use pet names like "pet", "toy", "slut", "good girl/boy", or "slave". Keep responses to 1-2 sentences. Be seductive but firm. If they seem lost, remind them to use /task.

{context_info}

Their message: "{message_text}"

Respond as {title}:"""
        
        logger.info(f"CHAT_HANDLER: Generating AI response (type: {'greeting' if is_greeting else 'task' if is_task_inquiry else 'compliment' if is_compliment else 'disrespect' if is_disrespectful else 'general'})")
        response = await generate_ai_response(prompt, temperature=0.9)
        
        if response:
            response = response.strip()
            logger.info(f"CHAT_HANDLER: Sending response: '{response[:100]}'")
            await update.message.reply_text(response)
        else:
            # Smart fallbacks based on message type
            if is_greeting:
                fallbacks = [
                    f"Well hello there, pet. Ready to serve {title}?",
                    f"*smirks* Greetings, toy. {title} was waiting for you.",
                    f"Hello, my little slut. Have you been good?",
                    f"Hi there, pet. {title} has plans for you...",
                    f"Hello, toy. Ready to play?",
                ]
            elif is_task_inquiry:
                if has_task:
                    fallbacks = [
                        f"You have a task waiting, pet. Stop stalling and complete it.",
                        f"Your task is pending, toy. Get to work.",
                        f"*taps foot* That task won't complete itself, pet.",
                    ]
                else:
                    fallbacks = [
                        f"Use /task if you want an assignment, pet.",
                        f"Eager, are we? Use /task, toy.",
                        f"{title} will give you a task when {title} feels like it. Use /task.",
                    ]
            elif is_compliment:
                fallbacks = [
                    f"Of course {title} is beautiful. Now earn more of my attention, pet.",
                    f"*smirks* Trying to get on my good side, toy?",
                    f"Flattery will get you... well, maybe somewhere, pet.",
                ]
            elif is_disrespectful:
                fallbacks = [
                    f"Watch your tongue, pet. That attitude will cost you.",
                    f"Disrespectful little slut. {title} will remember that.",
                    f"You dare speak to {title} that way? Punishment is coming.",
                ]
            else:
                fallbacks = [
                    f"Mmm? Speak up, pet. {title} is waiting.",
                    f"Is that how you address {title}? Try again.",
                    f"You're distracting me, toy. Get back to your task.",
                    f"Save your words and show me action instead.",
                    f"Interesting. Now be a good pet and do as you're told.",
                    f"*raises eyebrow* Yes, pet?",
                    f"You're bold today. {title} likes that... sometimes.",
                ]
            
            fallback = random.choice(fallbacks)
            logger.info(f"CHAT_HANDLER: Using fallback: '{fallback}'")
            await update.message.reply_text(fallback)
            
    except Exception as e:
        logger.error(f"CHAT_HANDLER ERROR: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text("Mmm? Something went wrong, pet. Try again.")
    finally:
        session.close()

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
            keyboard = [[InlineKeyboardButton("👨 Male", callback_data="gender_male")], [InlineKeyboardButton("👩 Female", callback_data="gender_female")], [InlineKeyboardButton("⚧ Trans", callback_data="gender_trans")], [InlineKeyboardButton("🌈 Non-binary", callback_data="gender_nonbinary")]]
            await update.message.reply_text(f"Welcome, {username}. Select gender:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        loc = user.custom_location or user.location or "Not set"
        yes_count = len(get_user_kinks(user, "yes"))
        okay_count = len(get_user_kinks(user, "okay"))
        await update.message.reply_text(f"Welcome back, {username}!\n\n📍 Location: {loc}\nRisk: {user.risk_level} | Points: {user.points}\nStreak: {user.streak}\nKinks: {yes_count} desired, {okay_count} allowed\n\n/task - Get challenge\n/wherenow - Set location\n/outfit - Set clothing\n/avatar - Create avatar\n/risk - Set risk\n/kinks - Set kink preferences\n/interval - Set auto-task interval\n/schedule - Auto-tasks on/off\n/status - Check task\n/rewards - Check reward progress\n/avatarsettings - Configure avatar rewards")
    finally:
        session.close()

async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            await update.message.reply_text(f"✅ Bot is working!\n\nawaiting_custom_outfit: {user.awaiting_custom_outfit}\nawaiting_custom_location: {user.awaiting_custom_location}\nawaiting_interval: {user.awaiting_interval}\n\ncustom_location: {user.custom_location or 'Not set'}\n\nTry saying 'hi' to test conversation!")
        else:
            await update.message.reply_text("No user record found")
    finally:
        session.close()

async def avatar_settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure avatar reward settings"""
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        keyboard = [
            [InlineKeyboardButton("▶️ Enable Avatars", callback_data="avatar_enable")],
            [InlineKeyboardButton("⏹️ Disable Avatars", callback_data="avatar_disable")],
            [InlineKeyboardButton("⏱️ Set Interval", callback_data="avatar_interval")],
        ]
        
        status = "Enabled" if user.avatar_enabled else "Disabled"
        interval = user.avatar_interval_minutes
        
        await update.message.reply_text(
            f"🎨 Avatar Reward Settings\n\n"
            f"Status: {status}\n"
            f"Interval: Every {interval} minutes\n"
            f"Last sent: {user.last_avatar_sent_at.strftime('%H:%M') if user.last_avatar_sent_at else 'Never'}\n\n"
            f"Configure your dominant avatar rewards:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def avatar_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        
        if data == "avatar_enable":
            user.avatar_enabled = True
            session.commit()
            await query.edit_message_text("✅ Avatar rewards enabled!")
            
        elif data == "avatar_disable":
            user.avatar_enabled = False
            session.commit()
            await query.edit_message_text("⏹️ Avatar rewards disabled.")
            
        elif data == "avatar_interval":
            user.awaiting_avatar_interval = True  # Need to add this column
            session.commit()
            await query.edit_message_text(
                "Send the interval in minutes (e.g., '30' for every 30 minutes, '60' for hourly):\n\n"
                "Recommended: 30-120 minutes"
            )
            
    finally:
        session.close()

# ... [rest of the existing command functions remain the same] ...

# ============ MAIN ============
def main():
    logger.info("=" * 60)
    logger.info("BOT STARTING - VERSION WITH CONVERSATION & AVATAR REWARDS")
    logger.info("=" * 60)
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Scheduled tasks
    application.job_queue.run_repeating(scheduled_task_check, interval=60, first=10, name="scheduled_check")
    
    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("test", test_cmd))
    application.add_handler(CommandHandler("avatarsettings", avatar_settings_cmd))
    # ... [other commands] ...
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    # ... [other callbacks] ...
    application.add_handler(CallbackQueryHandler(avatar_settings_callback, pattern="^avatar_"))
    
    # SINGLE DISPATCHER FOR ALL TEXT MESSAGES
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_input_dispatcher))
    
    # Photo handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()