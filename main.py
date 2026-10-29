import os
import re
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

from PIL import Image, UnidentifiedImageError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, DateTime, Boolean, Text, desc
from sqlalchemy.orm import declarative_base, sessionmaker

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
    outfit_detail = Column(Text, default=None)
    location = Column(String(50), default=None)
    custom_location = Column(String(100), default=None)
    location_detail = Column(Text, default=None)
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
    recent_settings = Column(Text, default=None)
    awaiting_custom_outfit = Column(Boolean, default=False)
    awaiting_outfit_detail = Column(Boolean, default=False)
    awaiting_custom_location = Column(Boolean, default=False)
    awaiting_location_detail = Column(Boolean, default=False)
    awaiting_interval = Column(Boolean, default=False)
    last_avatar_sent_at = Column(DateTime(timezone=True), nullable=True)
    avatar_interval_minutes = Column(Integer, default=60)
    avatar_enabled = Column(Boolean, default=True)
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
    followup_target = Column(Text, nullable=True)
    blocked_count = Column(Integer, default=0)

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

class LocationConstraint(Base):
    __tablename__ = 'location_constraints'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    location = Column(String(100), nullable=False)
    constraint = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    times_hit = Column(Integer, default=1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# ============ IMAGE HANDLING ============
def normalize_for_telegram(image_bytes, max_side=1600):
    """Decode any image format and re-encode as baseline JPEG for Telegram."""
    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        logger.error(f"Undecodable image: {e}")
        return None
    try:
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        out = BytesIO()
        img.save(out, format="JPEG", quality=92, progressive=False, optimize=True)
        return out.getvalue()
    except Exception as e:
        logger.error(f"Image normalize error: {e}")
        return None

def dump_debug(image_bytes, user_id, kind="raw"):
    try:
        with open(f"/tmp/avatar_{kind}_{user_id}.bin", "wb") as f:
            f.write(image_bytes)
    except Exception as e:
        logger.warning(f"Debug dump failed: {e}")

# ============ CLOUDINARY HELPERS ============
async def upload_to_cloudinary(image_bytes, user_id, image_type='user_upload', folder='telegram_bot'):
    try:
        if isinstance(image_bytes, (bytes, bytearray)):
            image_bytes = BytesIO(image_bytes)
        image_bytes.seek(0)
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        public_id = f"{folder}/user_{user_id}/{image_type}_{timestamp}_{random.randint(1000, 9999)}"
        result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            image_bytes,
            public_id=public_id,
            resource_type="image",
            context={'user_id': str(user_id), 'image_type': image_type, 'uploaded_at': str(datetime.now(timezone.utc))},
            tags=[f"user_{user_id}", image_type, "telegram_bot"]
        )
        logger.info(f"Cloudinary upload success: {result.get('public_id')}")
        return {'url': result.get('secure_url'), 'public_id': result.get('public_id'), 'width': result.get('width'), 'height': result.get('height')}
    except Exception as e:
        logger.error(f"Cloudinary upload error: {type(e).__name__}: {e}")
        return None

# ============ CONSTANTS ============
RISK_LEVELS = {
    1: {"name": "Safe", "description": "Private, no exposure, completely controlled environment"},
    2: {"name": "Low", "description": "Private with minor vulnerability (unlocked door, thin walls)"},
    3: {"name": "Medium", "description": "Semi-private (near windows, balcony, could be heard/seen)"},
    4: {"name": "High", "description": "Semi-public (visible areas, shared spaces, immediate exposure risk)"},
    5: {"name": "Extreme", "description": "Public-adjacent (hallways, stairwells, high exposure possible)"}
}

LOCATION_PROBES = {
    "Hotel": [("gym", "🏋️ Gym"), ("pool", "🏊 Pool"), ("sauna", "🧖 Sauna"), ("corridor", "🚪 Corridor"), ("elevator", "🛗 Lift"), ("lobby", "🛎️ Lobby"), ("balcony", "🌤️ Balcony"), ("bathtub", "🛁 Bathtub"), ("parking", "🅿️ Parking"), ("laundry", "🧺 Laundry room")],
    "Home": [("garden", "🌳 Garden"), ("garage", "🚗 Garage"), ("balcony", "🌤️ Balcony"), ("shed", "🏚️ Shed"), ("bathroom", "🛁 Bathroom"), ("hallway", "🚪 Hallway"), ("laundry", "🧺 Laundry room"), ("stairs", "🪜 Stairs"), ("attic", "📦 Attic")],
    "Retail Store": [("dressing", "🚪 Changing room"), ("backroom", "📦 Stockroom"), ("bathroom", "🚻 Store bathroom"), ("parking", "🅿️ Parking lot"), ("alley", "🌑 Alley"), ("loading", "🚚 Loading dock")],
    "Vehicle": [("empty_lot", "🅿️ Empty lot"), ("busy_lot", "🚗 Busy lot"), ("rest_stop", "🛑 Rest stop"), ("gas", "⛽ Petrol station"), ("backseat", "🪑 Back seat"), ("highway", "🛣️ Highway")],
    "Work": [("office", "🚪 Private office"), ("stairwell", "🪜 Stairwell"), ("conference", "🪑 Empty meeting room"), ("bathroom", "🚻 Bathroom"), ("garage", "🅿️ Parking garage"), ("rooftop", "🏙️ Rooftop"), ("elevator", "🛗 Lift")],
    "Generic": [("window", "🪟 Window"), ("doorway", "🚪 Doorway"), ("mirror", "🪞 Mirror"), ("bathroom", "🛁 Bathroom"), ("outside", "🌤️ Outside"), ("floor", "🧎 Floor")]
}

def get_probe_key(location):
    low = (location or "").lower()
    for key in LOCATION_PROBES:
        if key != "Generic" and key.lower() in low:
            return key
    return "Generic"

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

def task_keyboard(task_id, title):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📸 Done, {title}", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton("🚧 Not possible", callback_data=f"blocked_{task_id}")],
        [InlineKeyboardButton("❌ I can't...", callback_data=f"giveup_{task_id}")],
        [InlineKeyboardButton("🙏 Mercy", callback_data=f"mercy_{task_id}")],
    ])

async def generate_ai_response(prompt, temperature=0.9):
    try:
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "claude-opus-4-8-fast", "messages": [{"role": "system", "content": "You are a playful but demanding Domme. Speak with confidence, occasional teasing, and personality. Be conversational, use pet names, mix encouragement with demands."}, {"role": "user", "content": prompt}], "temperature": temperature, "max_tokens": 500}
        response = await asyncio.to_thread(
            requests.post, f"{VENICE_API_URL}/chat/completions",
            headers=headers, json=data, timeout=30
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        logger.error(f"AI error: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"AI error: {e}")
        return None

async def analyze_image(image_bytes, task_desc, followup_target=None):
    """Returns raw verifier text, or None on transport failure."""
    try:
        headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        if followup_target:
            prompt = f"""The sub was asked for ONE specific thing after an earlier photo: {followup_target}
The original task was: {task_desc}

Judge ONLY whether {followup_target} is clearly visible in this photo. Ignore everything else about the task.
Be lenient. If it is reasonably visible, pass it.

Reply in exactly this format:
VERIFIED: yes/no
MISSING: <the single thing still not visible, or "none">
REASON: brief"""
        else:
            prompt = f"""Task: {task_desc}

Judge whether this photo shows the task was done. Be LENIENT:
- The sub is holding the phone in one hand, so full-body framing is often impossible.
- Selfies mean they cannot see their own framing; partial crops are normal.
- Any equivalent item counts (any clamp = clothespin, any tie = rope).
- Judge only the PRIMARY element of the task. If the primary element is present, pass.

Reply in exactly this format:
VERIFIED: yes/no
MISSING: <the single most important element not visible, or "none">
REASON: brief"""
        data = {"model": "claude-opus-4-8-fast", "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}], "max_tokens": 200}
        response = await asyncio.to_thread(
            requests.post, f"{VENICE_API_URL}/chat/completions",
            headers=headers, json=data, timeout=30
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        logger.error(f"Vision error: HTTP {response.status_code} - {response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Vision error: {e}")
        return None

def parse_verification(response):
    """Line-based parse. Tolerates case, spacing and field reordering."""
    verified = "no"
    missing = None
    reason = "No reason given"
    if not response:
        return verified, missing, "Verifier returned nothing"
    for line in response.splitlines():
        line = line.strip()
        m = re.match(r"VERIFIED:\s*(yes|no)", line, re.IGNORECASE)
        if m:
            verified = m.group(1).lower()
            continue
        m = re.match(r"MISSING:\s*(.+)", line, re.IGNORECASE)
        if m:
            val = m.group(1).strip().rstrip('.')
            missing = None if val.lower() in ("none", "n/a", "-", "nothing") else val
            continue
        m = re.match(r"REASON:\s*(.+)", line, re.IGNORECASE)
        if m:
            reason = m.group(1).strip()
    return verified, missing, reason

async def generate_task_text(user, session=None, depth=0):
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
    outfit_text = user.outfit_detail or ", ".join(outfit_items) or "clothing"
    detail = user.location_detail or ""
    guide = GENDER_GUIDELINES.get(gender, GENDER_GUIDELINES["nonbinary"])
    body_parts = ", ".join(guide["body_parts"])
    yes_kinks = get_user_kinks(user, "yes")
    okay_kinks = get_user_kinks(user, "okay")
    forbidden_kinks = []
    for k in KINK_CATEGORIES.keys():
        if getattr(user, k, "no") == "no":
            forbidden_kinks.append(k.replace("kink_", ""))
    all_allowed = yes_kinks + okay_kinks
    if not all_allowed:
        return f"Strip completely at {location} and take a photo.", actual_risk
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

    recent_settings = json.loads(user.recent_settings or '[]')
    recent_text = "\n".join(f"- {r}" for r in recent_settings[-8:]) if recent_settings else "none yet"
    blockers = []
    if session:
        blockers = session.query(LocationConstraint).filter(
            LocationConstraint.user_id == user.user_id,
            LocationConstraint.location == location,
            LocationConstraint.expires_at > datetime.now(timezone.utc)
        ).all()
    blockers_text = "\n".join(f"- {b.constraint}" for b in blockers) if blockers else "none"

    risk_desc = RISK_LEVELS[actual_risk]["description"]
    yes_text = f"\nDESIRED: {', '.join(yes_kinks)}" if yes_kinks else ""
    selected_text = f"\nUSE: {', '.join(selected_kinks)}"
    forbidden_text = f"\n\nNEVER: {', '.join(forbidden_kinks)}" if forbidden_kinks else ""
    prompt = f"""Create ONE BDSM task for a {gender} sub.

Location: {location}
Venue detail and props within reach: {detail or "nothing beyond the basic space"}
Context: {others}, {privacy} privacy
Risk: {actual_risk}/5 - {risk_desc}
Wearing: {user.current_outfit} - {outfit_text}
Body parts: {body_parts}{yes_text}{selected_text}{forbidden_text}

KNOWN BLOCKERS AT THIS LOCATION - do not build tasks around these:
{blockers_text}

RECENTLY USED HERE - prefer variety, but reuse is fine if it genuinely fits better:
{recent_text}

Work in this order:
1. Silently list 10 specific settings this exact place contains. Use the venue detail first, then the props in reach, then what the place obviously has. Be concrete: "the luggage rack", "the bathroom door left ajar", "the wardrobe mirror" - not "the room".
2. Cross off anything ruled out by the blockers.
3. Choose the setting that best supports risk {actual_risk}/5, leaning towards whatever has been used least. Exposure settings are not automatically better - a mirror, a piece of furniture or a specific corner usually beats another window.
4. Write the task around that setting.

Rules:
- Single action, photo proof required
- No time durations
- Never use forbidden kinks
- The sub photographs with ONE hand. If the action needs both hands, state a concrete way to take the shot (propped phone, timer, mirror).
- Name the setting explicitly in the task
- Trust the outfit description over the outfit label. If she says no underwear, do not reference panties.
- Favour the specific and unexpected over the generic

Reply in this format:
TASK: <the task, naming the setting>
SETTING: <the setting, 2-5 words>"""
    response = await generate_ai_response(prompt, temperature=0.95)
    if response:
        response = response.strip()
        forbidden_keywords = {"marking": ["write", "marker", "sharpie", "draw on", "body writing", "written", "label"], "watersports": ["pee", "piss", "urine", "wet yourself"], "breathplay": ["choke", "strangle", "suffocate"], "social_media": ["post", "upload", "instagram", "twitter", "facebook", "share online"]}
        for forbidden_kink, keywords in forbidden_keywords.items():
            if depth < 3 and forbidden_kink in forbidden_kinks:
                if any(kw in response.lower() for kw in keywords):
                    logger.warning(f"Filtered forbidden kink '{forbidden_kink}'")
                    return await generate_task_text(user, session, depth + 1)
        setting = None
        kept = []
        for line in response.splitlines():
            stripped = line.strip()
            m = re.match(r"SETTING:\s*(.+)", stripped, re.IGNORECASE)
            if m:
                setting = m.group(1).strip()
                continue
            m = re.match(r"TASK:\s*(.+)", stripped, re.IGNORECASE)
            kept.append(m.group(1).strip() if m else line)
        response = "\n".join(l for l in kept if l.strip()).strip()
        if setting:
            recent_settings.append(setting)
            user.recent_settings = json.dumps(recent_settings[-8:])
            if session:
                session.commit()
        if response:
            return response, actual_risk
    fallbacks = {1: f"Strip completely at {location} and photograph your reflection", 2: f"Strip at {location} near the unlocked door and take a photo", 3: f"Expose yourself at {location} near a window and photograph the view", 4: f"Step just outside {location} doorway, expose yourself, and take a photo", 5: f"Walk to the end of the {location} hallway, expose yourself briefly, photograph the empty hall behind you"}
    return fallbacks.get(actual_risk, fallbacks[1]), actual_risk

# ============ AVATAR ============
IMAGE_PAYLOAD_BASE = {"model": "chroma", "width": 832, "height": 1216, "format": "jpeg", "steps": 30, "cfg_scale": 7}

async def _request_image(prompt):
    headers = {"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"}
    data = dict(IMAGE_PAYLOAD_BASE)
    data["prompt"] = prompt
    data["seed"] = random.randint(1, 1000000)
    response = await asyncio.to_thread(
        requests.post, VENICE_IMAGE_URL, headers=headers, json=data, timeout=90
    )
    logger.info(f"Image API status: {response.status_code}")
    if response.status_code != 200:
        logger.error(f"Image API error: {response.status_code} - {response.text[:300]}")
        return None
    result = response.json()
    if not result.get('images'):
        logger.error(f"Image API returned no images: {str(result)[:300]}")
        return None
    image_data = result['images'][0]
    raw = None
    if isinstance(image_data, str) and image_data.startswith('http'):
        img_response = await asyncio.to_thread(requests.get, image_data, timeout=30)
        if img_response.status_code == 200:
            raw = img_response.content
    elif isinstance(image_data, str) and image_data.startswith('data:image'):
        raw = base64.b64decode(image_data.split(',')[1])
    elif isinstance(image_data, str):
        try:
            raw = base64.b64decode(image_data)
        except Exception as e:
            logger.error(f"Base64 decode failed: {e}")
            return None
    elif isinstance(image_data, bytes):
        raw = image_data
    if not raw:
        logger.error("No image data extracted")
        return None
    return raw

async def _build_and_send(user, prompt, user_id=None):
    raw = await _request_image(prompt)
    if not raw:
        return None
    if user_id:
        await asyncio.to_thread(dump_debug, raw, user_id, "raw")
    normalized = await asyncio.to_thread(normalize_for_telegram, raw)
    if normalized and user_id:
        await asyncio.to_thread(dump_debug, normalized, user_id, "norm")
        logger.info(f"Raw {len(raw)}b -> normalized {len(normalized)}b")
    return normalized

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
            prompt = f"Beautiful {race_desc} {gender}, {build_desc}, {hair} hair, {size_desc}, completely nude, erotic submissive pose, sharp focus, detailed skin, high quality"
        else:
            pose = random.choice(DOMINANT_POSES)
            outfit = random.choice(DOMINANT_OUTFITS)
            prompt = f"Beautiful {race_desc} {gender}, {build_desc}, {hair} hair, {size_desc}, wearing {outfit}, {pose}, dominant attitude, sharp focus, detailed skin, high quality"
        return await _build_and_send(user, prompt, user.user_id)
    except Exception as e:
        logger.error(f"Avatar error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

async def generate_avatar_pose_image(gender, race, build, hair, size, user_id=None):
    try:
        gender_desc = AVATAR_GENDERS[gender]['desc']
        race_desc = AVATAR_RACES[race]['name'].split('/')[0]
        build_desc = AVATAR_BUILDS[build]['desc']
        size_desc = AVATAR_SIZES[size].get(gender, AVATAR_SIZES[size]['female'])
        if gender == "trans":
            prompt = f"Beautiful feminine {race_desc} trans woman, {build_desc}, {hair} hair, {size_desc}, nude, erotic pose, submissive, sharp focus, detailed skin, high quality"
        else:
            prompt = f"Beautiful {race_desc} {gender_desc}, {build_desc}, {hair} hair, {size_desc}, nude, erotic pose, submissive, sharp focus, detailed skin, high quality"
        return await _build_and_send(None, prompt, user_id)
    except Exception as e:
        logger.error(f"Avatar error: {e}")
        return None

async def send_avatar_photo(context, chat_id, image_bytes, caption):
    try:
        if not image_bytes or len(image_bytes) < 1000:
            logger.error(f"Invalid image bytes: {len(image_bytes) if image_bytes else 'None'}")
            return False
        buf = BytesIO(image_bytes)
        buf.seek(0)
        await context.bot.send_photo(chat_id=chat_id, photo=buf, caption=caption)
        return True
    except Exception as e:
        logger.error(f"Send photo error: {e}")
    return False

# ============ CUSTOM INPUT DISPATCHER ============
async def custom_input_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await chat_handler(update, context)
            return
        if user.awaiting_custom_outfit:
            await handle_custom_outfit(update, context)
            return
        elif user.awaiting_outfit_detail:
            await handle_outfit_detail(update, context)
            return
        elif user.awaiting_custom_location:
            await handle_custom_location(update, context)
            return
        elif user.awaiting_location_detail:
            await handle_location_detail(update, context)
            return
        elif user.awaiting_interval:
            await handle_interval_input(update, context)
            return
        elif context.user_data.get('blocked_task_id'):
            await handle_blocker_input(update, context)
            return
        await chat_handler(update, context)
    finally:
        session.close()

# ============ ENHANCED CHAT HANDLER ============
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    message_lower = message_text.lower()
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
- Current outfit: {user.outfit_detail or user.current_outfit or 'unknown'}
- Location: {user.custom_location or user.location or 'unknown'}
- Points: {user.points}
- Streak: {user.streak}
- Risk level: {user.risk_level}/5
- Has active task: {'Yes' if has_task else 'No'}
- Tasks completed: {user.completed_tasks}
"""
        is_greeting = any(greet in message_lower for greet in GREETINGS)
        is_task_inquiry = any(inquiry in message_lower for inquiry in TASK_INQUIRIES)
        is_compliment = any(comp in message_lower for comp in COMPLIMENTS)
        is_disrespectful = any(disp in message_lower for disp in DISRESPECTFUL)
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
            prompt = f"""You are a dominant {title} addressing your submissive. Be playful, teasing, and commanding. Use pet names like "pet", "toy", "slut", "good girl/boy", or "slave". Keep responses to 1-2 sentences. Be seductive but firm. If they seem lost, remind them to use /task.

{context_info}

Their message: "{message_text}"

Respond as {title}:"""
        response = await generate_ai_response(prompt, temperature=0.9)
        if response:
            await update.message.reply_text(response.strip())
        else:
            if is_greeting:
                fallbacks = [f"Well hello there, pet. Ready to serve {title}?", f"*smirks* Greetings, toy. {title} was waiting for you.", f"Hello, my little slut. Have you been good?", f"Hi there, pet. {title} has plans for you...", f"Hello, toy. Ready to play?"]
            elif is_task_inquiry:
                if has_task:
                    fallbacks = [f"You have a task waiting, pet. Stop stalling and complete it.", f"Your task is pending, toy. Get to work.", f"*taps foot* That task won't complete itself, pet."]
                else:
                    fallbacks = [f"Use /task if you want an assignment, pet.", f"Eager, are we? Use /task, toy.", f"{title} will give you a task when {title} feels like it. Use /task."]
            elif is_compliment:
                fallbacks = [f"Of course {title} is beautiful. Now earn more of my attention, pet.", f"*smirks* Trying to get on my good side, toy?", f"Flattery will get you... well, maybe somewhere, pet."]
            elif is_disrespectful:
                fallbacks = [f"Watch your tongue, pet. That attitude will cost you.", f"Disrespectful little slut. {title} will remember that.", f"You dare speak to {title} that way? Punishment is coming."]
            else:
                fallbacks = [f"Mmm? Speak up, pet. {title} is waiting.", f"Is that how you address {title}? Try again.", f"You're distracting me, toy. Get back to your task.", f"Save your words and show me action instead.", f"Interesting. Now be a good pet and do as you're told.", f"*raises eyebrow* Yes, pet?", f"You're bold today. {title} likes that... sometimes."]
            await update.message.reply_text(random.choice(fallbacks))
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
        await update.message.reply_text(f"Welcome back, {username}!\n\n📍 Location: {loc}\nRisk: {user.risk_level} | Points: {user.points}\nStreak: {user.streak}\nKinks: {yes_count} desired, {okay_count} allowed\n\n/task - Get challenge\n/wherenow - Set location\n/outfit - Set clothing\n/avatar - Create avatar\n/risk - Set risk\n/kinks - Set kink preferences\n/interval - Set auto-task interval\n/schedule - Auto-tasks on/off\n/status - Check task\n/rewards - Check reward progress")
    finally:
        session.close()

async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            await update.message.reply_text(f"✅ Bot is working!\n\nflags: outfit={user.awaiting_custom_outfit}/{user.awaiting_outfit_detail}, loc={user.awaiting_custom_location}/{user.awaiting_location_detail}, interval={user.awaiting_interval}\n\nlocation: {user.custom_location or 'Not set'}\ndetail: {user.location_detail or 'none'}\noutfit: {user.outfit_detail or 'none'}\n\nTry saying 'hi' to test conversation!")
        else:
            await update.message.reply_text("No user record found")
    finally:
        session.close()

async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.awaiting_location_detail = False
            user.awaiting_outfit_detail = False
            user.awaiting_custom_outfit = False
            user.awaiting_custom_location = False
            session.commit()
        await update.message.reply_text("Fine - I'll work with what I have. Use /task.")
    finally:
        session.close()

async def gender_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("👨 Male", callback_data="gender_male")], [InlineKeyboardButton("👩 Female", callback_data="gender_female")], [InlineKeyboardButton("⚧ Trans", callback_data="gender_trans")], [InlineKeyboardButton("🌈 Non-binary", callback_data="gender_nonbinary")]]
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
        current = user.outfit_detail or user.current_outfit or "Not set"
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
            user.awaiting_custom_outfit = True
            session.commit()
            await query.edit_message_text("Describe your outfit:")
            return
        outfit = OUTFIT_OPTIONS[outfit_key]
        items = outfit.get(f"{user.gender}_items", outfit["male_items"])
        user.current_outfit = outfit["name"]
        user.outfit_items = json.dumps(items)
        user.outfit_detail = None
        user.awaiting_outfit_detail = True
        session.commit()
        await query.edit_message_text(f"{outfit['emoji']} {outfit['name']} - roughly.\n\nWhat are you actually in? Be specific, it changes what I can ask for. Type it, or /skip.")
    finally:
        session.close()

async def handle_custom_outfit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        user.awaiting_custom_outfit = False
        user.awaiting_outfit_detail = False
        custom = update.message.text.strip()
        user.current_outfit = f"Custom: {custom[:50]}"
        user.outfit_detail = custom[:300]
        items = [i.strip() for i in custom.split(',')]
        user.outfit_items = json.dumps(items[:6])
        session.commit()
        await update.message.reply_text("✅ Outfit saved. Use /wherenow!")
    finally:
        session.close()

async def handle_outfit_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        user.awaiting_outfit_detail = False
        user.outfit_detail = update.message.text.strip()[:300]
        session.commit()
        await update.message.reply_text("Noted. Use /wherenow.")
    finally:
        session.close()

async def wherenow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏪 Store", callback_data="ctx_store")], [InlineKeyboardButton("🏠 Home", callback_data="ctx_home")], [InlineKeyboardButton("🏨 Hotel", callback_data="ctx_hotel")], [InlineKeyboardButton("🚗 Vehicle", callback_data="ctx_car")], [InlineKeyboardButton("🏢 Work", callback_data="ctx_work")], [InlineKeyboardButton("✏️ Custom", callback_data="ctx_custom")]]
    await update.message.reply_text("📍 Where are you?", reply_markup=InlineKeyboardMarkup(keyboard))

async def context_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    ctx_type = query.data.replace("ctx_", "")
    if ctx_type == "custom":
        session = get_session()
        try:
            user = session.query(UserState).filter_by(user_id=user_id).first()
            if user:
                user.awaiting_custom_location = True
                session.commit()
                await query.edit_message_text("Describe exactly where you are:")
        finally:
            session.close()
        return
    loc_map = {"store": "Retail Store", "home": "Home", "hotel": "Hotel", "car": "Vehicle", "work": "Work"}
    location = loc_map.get(ctx_type, "Unknown")
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.location = location
            user.custom_location = location
            user.location_detail = None
            session.commit()
    finally:
        session.close()
    keyboard = [[InlineKeyboardButton("🧍 Alone", callback_data="present_alone")], [InlineKeyboardButton("💑 Partner", callback_data="present_partner")], [InlineKeyboardButton("🏠 Roommates", callback_data="present_roommates")], [InlineKeyboardButton("👨‍👩‍👧 Family", callback_data="present_parents")], [InlineKeyboardButton("👶 Kids", callback_data="present_kids")], [InlineKeyboardButton("👥 Public", callback_data="present_public")]]
    await query.edit_message_text(f"📍 {location}\n\nWho is present?", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_custom_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        user.awaiting_custom_location = False
        user.custom_location = update.message.text.strip()[:100]
        user.location = "Custom"
        user.location_detail = None
        session.commit()
        keyboard = [[InlineKeyboardButton("🧍 Alone", callback_data="present_alone")], [InlineKeyboardButton("💑 Partner", callback_data="present_partner")], [InlineKeyboardButton("🏠 Roommates", callback_data="present_roommates")], [InlineKeyboardButton("👥 Public", callback_data="present_public")]]
        await update.message.reply_text(f"📍 {user.custom_location}\n\nWho is present?", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

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
    keyboard = [[InlineKeyboardButton("🔒 Private", callback_data="privacy_private")], [InlineKeyboardButton("🚪 Semi-private", callback_data="privacy_semi")], [InlineKeyboardButton("👁️ Exposed", callback_data="privacy_exposed")], [InlineKeyboardButton("🌍 Public", callback_data="privacy_public")]]
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
        if not user:
            await query.edit_message_text("Use /start first")
            return
        user.context_privacy = privacy
        user.awaiting_location_detail = True
        session.commit()
        location = user.custom_location or user.location or "this place"
        await query.edit_message_text(
            f"Last thing - anything about {location} I should know?\n\n"
            f"What's within reach, how busy it is, anything you could grab to use. Type it, or /skip.",
            reply_markup=probe_keyboard(location, [])
        )
    finally:
        session.close()

async def handle_location_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        user.awaiting_location_detail = False
        text = update.message.text.strip()[:400]
        user.location_detail = f"{user.location_detail}, {text}" if user.location_detail else text
        session.commit()
        await update.message.reply_text("Good. That's enough to work with.\n\nUse /task.")
    finally:
        session.close()

# ============ VENUE CHIPS ============
def probe_keyboard(location, selected):
    keyboard = []
    for key, label in LOCATION_PROBES.get(get_probe_key(location), LOCATION_PROBES["Generic"]):
        mark = "✅ " if key in selected else ""
        keyboard.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"probe_{key}")])
    keyboard.append([InlineKeyboardButton("✔️ That's all", callback_data="probe_done")])
    return InlineKeyboardMarkup(keyboard)

async def probe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await query.edit_message_text("Use /start first")
            return
        location = user.custom_location or user.location or ""
        if query.data == "probe_done":
            user.awaiting_location_detail = False
            session.commit()
            await query.edit_message_text("Good - that gives me something to work with.\n\nUse /kinks if you haven't set preferences, then /task.")
            return
        feature = query.data.replace("probe_", "")
        labels = dict(LOCATION_PROBES.get(get_probe_key(location), LOCATION_PROBES["Generic"]))
        token = labels.get(feature, feature).split(" ", 1)[-1]
        detail = user.location_detail or ""
        if token.lower() in detail.lower():
            user.location_detail = re.sub(re.escape(token), "", detail, flags=re.IGNORECASE).strip(", ") or None
        else:
            user.location_detail = f"{detail}, {token}" if detail else token
        session.commit()
        current = [k for k, v in labels.items() if v.split(" ", 1)[-1].lower() in (user.location_detail or "").lower()]
        await query.edit_message_text(
            f"Noted. Anything else about {location or 'this place'}, or /skip when you're done.",
            reply_markup=probe_keyboard(location, current)
        )
    finally:
        session.close()

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
        await update.message.reply_text("🎭 Kink Preferences\n\n❌ = No (hard limit)\n⭕ = Okay (Dom may use)\n✅ = Yes (desired/favorite)\n\nTap a kink to cycle through options:", reply_markup=InlineKeyboardMarkup(keyboard))
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
        keyboard = [[InlineKeyboardButton(f"{'✅' if current == 'no' else ''} ❌ No (Never)", callback_data=f"kinkset_{kink_key}_no")], [InlineKeyboardButton(f"{'✅' if current == 'okay' else ''} ⭕ Okay (Dom decides)", callback_data=f"kinkset_{kink_key}_okay")], [InlineKeyboardButton(f"{'✅' if current == 'yes' else ''} ✅ Yes (Desired!)", callback_data=f"kinkset_{kink_key}_yes")], [InlineKeyboardButton("🔙 Back", callback_data="kinks_back")]]
        await query.edit_message_text(f"{name}\n\n{desc}\n\nCurrent: {KINK_LEVELS[current]['emoji']} {KINK_LEVELS[current]['name']}\n\nSelect new level:", reply_markup=InlineKeyboardMarkup(keyboard))
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
            await query.edit_message_text(f"✅ {name} set to {KINK_LEVELS[level]['emoji']} {KINK_LEVELS[level]['name']}")
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
        await query.edit_message_text("🎭 Kink Preferences\n\n❌ = No (hard limit)\n⭕ = Okay (Dom may use)\n✅ = Yes (desired/favorite)\n\nTap a kink to cycle through options:", reply_markup=InlineKeyboardMarkup(keyboard))
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
        user.awaiting_interval = True
        session.commit()
        await update.message.reply_text(f"⏱️ Auto-Task Interval\n\nCurrent: {user.min_interval}-{user.max_interval} minutes\n\nSend new interval as: MIN MAX\nExamples: '30 60' or '60 120'\n\nSend 'cancel' to keep current.")
    finally:
        session.close()

async def handle_interval_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        text = update.message.text.strip().lower()
        if text == 'cancel':
            user.awaiting_interval = False
            session.commit()
            await update.message.reply_text("Interval unchanged.")
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
            user.min_interval = min_int
            user.max_interval = max_int
            user.awaiting_interval = False
            session.commit()
            await update.message.reply_text(f"✅ Interval: {min_int}-{max_int} minutes")
        except ValueError:
            await update.message.reply_text("❌ Invalid format. Send as: MIN MAX")
    finally:
        session.close()

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data.pop('blocked_task_id', None)
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        user.awaiting_location_detail = False
        user.awaiting_outfit_detail = False
        session.commit()
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
        if random.random() < 0.3 and user.avatar_gender:
            avatar_bytes = await generate_avatar_pose(user, "dominant")
            if avatar_bytes:
                await send_avatar_photo(context, user_id, avatar_bytes, "Your task awaits...")
                await asyncio.sleep(1)
        task_text, actual_risk = await generate_task_text(user, session)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=30)
        task = Task(user_id=user_id, task_text=task_text, risk_level=actual_risk, created_at=now, expires_at=expires)
        session.add(task)
        session.commit()
        context.job_queue.run_once(auto_clear_task, when=expires, data={'user_id': user_id, 'task_id': task.id}, name=f"timeout_{task.id}")
        await update.message.reply_text(f"🎯 TASK\n\n{task_text}\n\n30 minutes.", reply_markup=task_keyboard(task.id, get_title(user.avatar_gender)))
    finally:
        session.close()

async def blocked_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.replace("blocked_", ""))
    context.user_data['blocked_task_id'] = task_id
    await query.edit_message_text("What's in the way? Tell me and I'll rework it around that.")

async def handle_blocker_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task_id = context.user_data.get('blocked_task_id')
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id, user_id=user_id, status="pending").first() if task_id else None
        if not task:
            context.user_data.pop('blocked_task_id', None)
            await update.message.reply_text("That task's gone. Use /task.")
            return
        if task.blocked_count >= 3:
            await update.message.reply_text("Three reworks already, pet. Use Mercy if it still won't work.")
            return
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            return
        context.user_data.pop('blocked_task_id', None)
        constraint_text = update.message.text.strip()[:200]
        location = user.custom_location or user.location or "Unknown"
        norm = constraint_text.lower().strip().rstrip('.')
        existing = None
        for c in session.query(LocationConstraint).filter_by(user_id=user_id, location=location).all():
            if c.constraint.lower().strip().rstrip('.') == norm:
                existing = c
                break
        now = datetime.now(timezone.utc)
        if existing:
            existing.times_hit += 1
            existing.expires_at = now + timedelta(days=30 if existing.times_hit >= 2 else 3)
        else:
            session.add(LocationConstraint(user_id=user_id, location=location, constraint=constraint_text, expires_at=now + timedelta(hours=3)))
        session.commit()
        await update.message.reply_text("Fair. Reworking it - same difficulty.")
        task.blocked_count += 1
        new_text, actual_risk = await generate_task_text(user, session)
        task.task_text = new_text
        task.risk_level = actual_risk
        task.verification_attempts = 0
        task.followup_target = None
        task.expires_at = now + timedelta(minutes=30)
        session.commit()
        try:
            context.job_queue.run_once(auto_clear_task, when=timedelta(minutes=30), data={'user_id': user_id, 'task_id': task.id}, name=f"timeout_{task.id}")
        except Exception as e:
            logger.warning(f"Could not re-arm blocked timer: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"🎯 REWORKED\n\n{new_text}\n\n30 minutes.", reply_markup=task_keyboard(task.id, get_title(user.avatar_gender)))
    finally:
        session.close()

async def mercy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.replace("mercy_", ""))
    user_id = update.effective_user.id
    context.user_data.pop('blocked_task_id', None)
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id, user_id=user_id, status="pending").first()
        if not task:
            await query.edit_message_text("No active task.")
            return
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await query.edit_message_text("Use /start first")
            return
        await query.edit_message_text("Mercy granted, pet. Let me find something else...")
        new_task_text, actual_risk = await generate_task_text(user, session)
        now = datetime.now(timezone.utc)
        task.task_text = new_task_text
        task.risk_level = actual_risk
        task.verification_attempts = 0
        task.followup_target = None
        task.expires_at = now + timedelta(minutes=30)
        session.commit()
        try:
            context.job_queue.run_once(auto_clear_task, when=timedelta(minutes=30), data={'user_id': user_id, 'task_id': task.id}, name=f"timeout_{task.id}")
        except Exception as e:
            logger.warning(f"Could not re-arm mercy timer: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"🔄 NEW TASK (Mercy)\n\n{new_task_text}\n\n30 minutes.", reply_markup=task_keyboard(task.id, get_title(user.avatar_gender)))
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
            await update.message.reply_text(f"⏰ {max(0, time_left):.0f} min left\n\n{active.task_text[:200]}...", reply_markup=task_keyboard(active.id, get_title(user.avatar_gender)))
        else:
            loc = user.custom_location or user.location or "Not set"
            interval = f"{user.min_interval}-{user.max_interval} min" if user.scheduling_enabled else "Off"
            yes_kinks = len(get_user_kinks(user, "yes"))
            okay_kinks = len(get_user_kinks(user, "okay"))
            await update.message.reply_text(f"No active task.\n\n📍 {loc} | Points: {user.points} | Streak: {user.streak}\nKinks: {yes_kinks} desired, {okay_kinks} allowed\nAuto: {interval}\n\nUse /task!")
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
        await update.message.reply_text(f"🎁 Rewards unlock every 5-10 tasks completed.\n\nCurrent streak: {user.streak}\nTotal completed: {user.completed_tasks}\n\nKeep completing tasks to earn avatar rewards!")
    finally:
        session.close()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = get_session()
    try:
        task = session.query(Task).filter_by(user_id=user_id, status="pending").first()
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        await update.message.reply_text("Checking your photo...")
        photo_bytes = await file.download_as_bytearray()
        if len(photo_bytes) < 1000:
            await update.message.reply_text("Photo too small. Send clearer photo.")
            return
        cloudinary_result = await upload_to_cloudinary(photo_bytes, user_id, image_type='verification' if task else 'user_upload')
        session.add(UserImage(user_id=user_id, telegram_file_id=photo.file_id, cloudinary_url=cloudinary_result['url'] if cloudinary_result else None, cloudinary_public_id=cloudinary_result['public_id'] if cloudinary_result else None, image_type='verification' if task else 'user_upload'))
        session.commit()
        if not task:
            msg = "📸 Image saved to your collection."
            if cloudinary_result:
                msg += "\n☁️ Backed up to cloud."
            await update.message.reply_text(msg)
            return
        now = datetime.now(timezone.utc)
        if now > task.expires_at:
            task.status = "expired"
            session.commit()
            await update.message.reply_text("Task expired. Use /task.")
            return
        verification = await analyze_image(photo_bytes, task.task_text, task.followup_target)
        if verification is None:
            await update.message.reply_text("Couldn't reach the verifier just now - resend it, no attempt used.")
            return
        verified, missing, reason = parse_verification(verification)
        task.verification_attempts += 1
        if cloudinary_result:
            task.cloudinary_url = cloudinary_result['url']
            task.cloudinary_public_id = cloudinary_result['public_id']
        if verified == "yes":
            task.status = "completed"
            task.completed_at = now
            task.photo_url = photo.file_id
            task.followup_target = None
            context.user_data.pop('blocked_task_id', None)
            user = session.query(UserState).filter_by(user_id=user_id).first()
            if not user:
                await update.message.reply_text("Your profile is missing. Use /start.")
                return
            user.points += 10 * task.risk_level
            user.streak += 1
            user.completed_tasks += 1
            user.consecutive_failures = 0
            user.challenges_since_reward += 1
            session.commit()
            title = get_title(user.avatar_gender)
            if user.challenges_since_reward >= random.randint(5, 10):
                user.challenges_since_reward = 0
                session.commit()
                await update.message.reply_text(f"✅ +{10 * task.risk_level} points! Streak: {user.streak}\n\n🎁 Reward earned!")
                reward_bytes = await generate_avatar_pose(user, "reward")
                if reward_bytes:
                    reward_cloudinary = await upload_to_cloudinary(reward_bytes, user_id, image_type='reward')
                    await send_avatar_photo(context, user_id, reward_bytes, f"🎁 Your reward, {title} is pleased.")
                    if reward_cloudinary:
                        session.add(UserImage(user_id=user_id, telegram_file_id='generated', cloudinary_url=reward_cloudinary['url'], cloudinary_public_id=reward_cloudinary['public_id'], image_type='reward'))
                        session.commit()
                else:
                    await update.message.reply_text("🎁 Reward earned!")
            else:
                await update.message.reply_text(f"✅ +{10 * task.risk_level} points! Streak: {user.streak}")
        else:
            if task.verification_attempts >= 3:
                task.status = "failed"
                user = session.query(UserState).filter_by(user_id=user_id).first()
                if user:
                    user.consecutive_failures += 1
                session.commit()
                await update.message.reply_text(f"❌ Failed. {reason}")
            else:
                task.followup_target = missing
                session.commit()
                remaining = 3 - task.verification_attempts
                if missing:
                    text = f"Not quite, pet. I couldn't see {missing}.\n\nShow me {missing} - just that, nothing else."
                else:
                    text = f"Not quite. {reason}\n\nTry once more."
                keyboard = [[InlineKeyboardButton("🔄 Try Again", callback_data=f"retry_{task.id}")], [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]]
                await update.message.reply_text(f"{text}\n\n{remaining} {'try' if remaining == 1 else 'tries'} left.", reply_markup=InlineKeyboardMarkup(keyboard))
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
    context.user_data.pop('blocked_task_id', None)
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id, user_id=user_id).first()
        if task and task.status == "pending":
            task.status = "failed"
            user = session.query(UserState).filter_by(user_id=user_id).first()
            if user:
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

async def auto_clear_task(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    user_id = job_data['user_id']
    task_id = job_data['task_id']
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
        keyboard = [[InlineKeyboardButton(f"{g['emoji']} {g['name']}", callback_data=f"av_gender_{k}")] for k, g in AVATAR_GENDERS.items()]
        await update.message.reply_text("🎨 Create Your Avatar\n\nStep 1/5: Select gender:", reply_markup=InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

async def avatar_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("av_gender_", "")
    context.user_data['avatar_gender'] = gender
    keyboard = [[InlineKeyboardButton(f"{r['emoji']} {r['name']}", callback_data=f"av_race_{k}")] for k, r in AVATAR_RACES.items()]
    await query.edit_message_text(f"✅ Gender: {AVATAR_GENDERS[gender]['name']}\n\nStep 2/5: Select race:", reply_markup=InlineKeyboardMarkup(keyboard))

async def avatar_race_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    race = query.data.replace("av_race_", "")
    context.user_data['avatar_race'] = race
    keyboard = [[InlineKeyboardButton(f"{b['emoji']} {b['name']}", callback_data=f"av_build_{k}")] for k, b in AVATAR_BUILDS.items()]
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
    image_bytes = await generate_avatar_pose_image(gender, race, build, hair, size, user_id)
    if image_bytes:
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
            cloudinary_result = await upload_to_cloudinary(image_bytes, user_id, image_type='avatar')
            session.add(AvatarImage(user_id=user_id, image_url="generated", cloudinary_url=cloudinary_result['url'] if cloudinary_result else None, cloudinary_public_id=cloudinary_result['public_id'] if cloudinary_result else None, gender=gender, race=race, build=build))
            session.commit()
            await query.edit_message_text("✅ Avatar generated!")
            await send_avatar_photo(context, user_id, image_bytes, f"🎨 Your Avatar\nGender: {AVATAR_GENDERS[gender]['name']}\nRace: {AVATAR_RACES[race]['name']}\nBuild: {AVATAR_BUILDS[build]['name']}\nHair: {AVATAR_HAIR[hair]}\nSize: {AVATAR_SIZES[size]['name']}")
        finally:
            session.close()
    else:
        await query.edit_message_text("❌ Error generating avatar. Check /tmp/avatar_raw_*.bin and the log.")

# ============ SCHEDULER ============
async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("▶️ Enable", callback_data="sched_enable")], [InlineKeyboardButton("⏹️ Disable", callback_data="sched_disable")]]
    await update.message.reply_text("Auto-Task Scheduler:", reply_markup=InlineKeyboardMarkup(keyboard))

async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await query.edit_message_text("Use /start first")
            return
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

async def scheduled_task_check(context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    try:
        now = datetime.now(timezone.utc)
        session.query(LocationConstraint).filter(LocationConstraint.expires_at < now).delete()
        session.commit()
        users = session.query(UserState).filter(
            UserState.scheduling_enabled == True,
            UserState.next_task_time <= now
        ).all()
        for user in users:
            active = session.query(Task).filter_by(user_id=user.user_id, status="pending").first()
            if not active:
                try:
                    if random.random() < 0.3 and user.avatar_gender:
                        avatar_bytes = await generate_avatar_pose(user, "dominant")
                        if avatar_bytes:
                            await send_avatar_photo(context, user.user_id, avatar_bytes, "Your task awaits...")
                            await asyncio.sleep(1)
                    task_text, actual_risk = await generate_task_text(user, session)
                    expires = now + timedelta(minutes=30)
                    task = Task(user_id=user.user_id, task_text=task_text, risk_level=actual_risk, created_at=now, expires_at=expires)
                    session.add(task)
                    session.commit()
                    context.job_queue.run_once(auto_clear_task, when=expires, data={'user_id': user.user_id, 'task_id': task.id}, name=f"timeout_{task.id}")
                    await context.bot.send_message(chat_id=user.user_id, text=f"🎯 AUTO TASK\n\n{task_text}\n\n30 minutes.", reply_markup=task_keyboard(task.id, get_title(user.avatar_gender)))
                    user.next_task_time = now + timedelta(minutes=random.randint(user.min_interval, user.max_interval))
                    session.commit()
                except Exception as e:
                    logger.error(f"Auto-task error: {e}")
        avatar_users = session.query(UserState).filter(
            UserState.avatar_enabled == True,
            UserState.avatar_gender != None,
            UserState.last_avatar_sent_at <= now - timedelta(minutes=UserState.avatar_interval_minutes)
        ).all()
        for user in avatar_users:
            try:
                avatar_bytes = await generate_avatar_pose(user, "dominant")
                if avatar_bytes:
                    title = get_title(user.avatar_gender)
                    captions = ["Thinking of you, pet...", f"Your {title} is watching...", "Don't keep me waiting, toy.", "Ready to serve, pet?", "I have plans for you today..."]
                    await send_avatar_photo(context, user.user_id, avatar_bytes, random.choice(captions))
                    user.last_avatar_sent_at = now
                    session.commit()
            except Exception as e:
                logger.error(f"Periodic avatar error for user {user.user_id}: {e}")
    except Exception as e:
        logger.error(f"Scheduled check error: {e}")
    finally:
        session.close()

# ============ RESET ============
async def resetowner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("⚠️ YES DELETE ALL", callback_data="reset_confirm")], [InlineKeyboardButton("❌ Cancel", callback_data="reset_cancel")]]
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
        session.query(LocationConstraint).filter_by(user_id=user_id).delete()
        session.query(Task).filter_by(user_id=user_id).delete()
        session.query(TaskHistory).filter_by(user_id=user_id).delete()
        session.query(AvatarImage).filter_by(user_id=user_id).delete()
        session.query(UserImage).filter_by(user_id=user_id).delete()
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
    logger.info("=" * 60)
    logger.info("BOT STARTING")
    logger.info(f"Cloudinary configured: {bool(os.getenv('CLOUDINARY_CLOUD_NAME'))} / {bool(os.getenv('CLOUDINARY_API_KEY'))} / {bool(os.getenv('CLOUDINARY_API_SECRET'))}")
    logger.info("=" * 60)
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.job_queue.run_repeating(
        scheduled_task_check, interval=60, first=10, name="scheduled_check",
        job_kwargs={"misfire_grace_time": 180, "coalesce": True, "max_instances": 1}
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("test", test_cmd))
    application.add_handler(CommandHandler("skip", skip_cmd))
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
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    application.add_handler(CallbackQueryHandler(outfit_callback, pattern="^outfit_"))
    application.add_handler(CallbackQueryHandler(context_callback, pattern="^ctx_"))
    application.add_handler(CallbackQueryHandler(present_callback, pattern="^present_"))
    application.add_handler(CallbackQueryHandler(privacy_callback, pattern="^privacy_"))
    application.add_handler(CallbackQueryHandler(probe_callback, pattern="^probe_"))
    application.add_handler(CallbackQueryHandler(risk_callback, pattern="^risk_"))
    application.add_handler(CallbackQueryHandler(kink_menu_callback, pattern="^kinkmenu_"))
    application.add_handler(CallbackQueryHandler(kink_set_callback, pattern="^kinkset_"))
    application.add_handler(CallbackQueryHandler(kinks_back_callback, pattern="^kinks_back"))
    application.add_handler(CallbackQueryHandler(kinks_done_callback, pattern="^kinks_done"))
    application.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_"))
    application.add_handler(CallbackQueryHandler(blocked_callback, pattern="^blocked_"))
    application.add_handler(CallbackQueryHandler(giveup_callback, pattern="^giveup_"))
    application.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(schedule_callback, pattern="^sched_"))
    application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    application.add_handler(CallbackQueryHandler(avatar_gender_callback, pattern="^av_gender_"))
    application.add_handler(CallbackQueryHandler(avatar_race_callback, pattern="^av_race_"))
    application.add_handler(CallbackQueryHandler(avatar_build_callback, pattern="^av_build_"))
    application.add_handler(CallbackQueryHandler(avatar_hair_callback, pattern="^av_hair_"))
    application.add_handler(CallbackQueryHandler(avatar_size_callback, pattern="^av_size_"))
    application.add_handler(CallbackQueryHandler(mercy_callback, pattern="^mercy_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_input_dispatcher))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()