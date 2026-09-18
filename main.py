#!/usr/bin/env python3
"""
DOM Bot v9.1 - Ultimate Avatar Edition with Social Media Kink
Male, Female, Trans avatars with full customization
Risk & Creativity sliders, Social Media Exposure toggle
"""

import os
import logging
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set!")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)

VENVENICE_API_KEY = os.getenv('VENVENICE_API_KEY')
VENVENICE_MODEL = "claude-opus-4-8-fast"

# Avatar Configuration
GENDERS = ['male', 'female', 'trans']
ETHNICITIES = ['white', 'black', 'asian', 'hispanic']
BODY_TYPES = ['slim', 'average', 'muscular', 'curvy']
PUBIC_STYLES = ['shaved', 'trimmed', 'natural']
HAIR_COLORS = ['blonde', 'brown', 'red', 'black', 'white', 'bald']
FEMALE_SIZES = ['small', 'medium', 'large']
MALE_SIZES = ['small', 'medium', 'large']

# Kink categories - WITH SOCIAL MEDIA EXPOSURE
KINK_CATEGORIES = {
    'exposure': 'Public Exposure',
    'humiliation': 'Humiliation',
    'degradation': 'Degradation',
    'bondage': 'Bondage',
    'pain': 'Pain Play',
    'service': 'Service',
    'edging': 'Edging/Denial',
    'watersports': 'Watersports',
    'exhibitionism': 'Exhibitionism',
    'roleplay': 'Roleplay',
    'petplay': 'Pet Play',
    'feminization': 'Feminization',
    'masculinization': 'Masculinization',
    'CBT': 'CBT',
    'breathplay': 'Breath Play',
    'sensory': 'Sensory Play',
    'temperature': 'Temperature',
    'marking': 'Marking',
    'spanking': 'Spanking',
    'nipple': 'Nipple Play',
    'anal': 'Anal',
    'gags': 'Gags',
    'cuckold': 'Cuckold/Hotwife',
    'findom': 'Financial Domination',
    'hypno': 'Hypnosis',
    'blackmail': 'Blackmail Fantasy',
    'exposure_risk': 'Exposure Risk',
    'social_media': '📱 Social Media Exposure'  # NEW KINK
}

# Risk levels
RISK_LEVELS = {
    1: 'Safe (Home only)',
    2: 'Low (Minimal risk)',
    3: 'Medium (Semi-public)',
    4: 'High (Public possible)',
    5: 'Extreme (Dangerous)'
}

CREATIVITY_LEVELS = {
    1: 'Standard',
    2: 'Creative',
    3: 'Very Creative',
    4: 'Unpredictable',
    5: 'Chaotic'
}

# ==================== DATABASE MODELS ====================

class BotParameters(Base):
    __tablename__ = 'bot_parameters'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # All kinks - including social_media
    exposure = Column(Boolean, default=True)
    humiliation = Column(Boolean, default=True)
    degradation = Column(Boolean, default=True)
    bondage = Column(Boolean, default=True)
    pain = Column(Boolean, default=True)
    service = Column(Boolean, default=True)
    edging = Column(Boolean, default=True)
    watersports = Column(Boolean, default=True)
    exhibitionism = Column(Boolean, default=True)
    roleplay = Column(Boolean, default=True)
    petplay = Column(Boolean, default=True)
    feminization = Column(Boolean, default=True)
    masculinization = Column(Boolean, default=True)
    CBT = Column(Boolean, default=True)
    breathplay = Column(Boolean, default=True)
    sensory = Column(Boolean, default=True)
    temperature = Column(Boolean, default=True)
    marking = Column(Boolean, default=True)
    spanking = Column(Boolean, default=True)
    nipple = Column(Boolean, default=True)
    anal = Column(Boolean, default=True)
    gags = Column(Boolean, default=True)
    cuckold = Column(Boolean, default=False)
    findom = Column(Boolean, default=False)
    hypno = Column(Boolean, default=False)
    blackmail = Column(Boolean, default=False)
    exposure_risk = Column(Boolean, default=False)
    social_media = Column(Boolean, default=False)  # NEW COLUMN
    
    # Scheduling
    task_frequency_minutes = Column(Integer, default=60)
    last_task_sent = Column(DateTime)
    scheduling_enabled = Column(Boolean, default=True)
    
    # Stats
    total_tasks_completed = Column(Integer, default=0)
    total_tasks_failed = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    points = Column(Integer, default=0)
    
    # Current task
    current_task = Column(Text)
    task_assigned_at = Column(DateTime)
    task_completed = Column(Boolean, default=False)
    photo_retry_count = Column(Integer, default=0)
    
    # Avatar settings
    avatar_name = Column(String, default='Mistress')
    avatar_gender = Column(String, default='female')
    avatar_ethnicity = Column(String, default='white')
    avatar_body = Column(String, default='curvy')
    avatar_pubic = Column(String, default='trimmed')
    avatar_hair_color = Column(String, default='blonde')
    avatar_feature_size = Column(String, default='large')
    avatar_mood = Column(String, default='strict')
    
    # Sliders
    risk_level = Column(Integer, default=3)
    creativity_level = Column(Integer, default=3)
    
    # Rewards
    nude_reward_enabled = Column(Boolean, default=True)
    nude_frequency = Column(Integer, default=3)
    tasks_since_nude = Column(Integer, default=0)

class TaskHistory(Base):
    __tablename__ = 'task_history'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, nullable=False)
    task_description = Column(Text, nullable=False)
    risk_level = Column(Integer, default=3)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String, default='assigned')
    verification_photo_url = Column(String)
    feedback = Column(Text)

# Create tables
Base.metadata.create_all(engine)

# ==================== DATABASE HELPERS ====================

def get_user(chat_id: str, username: str = None) -> Dict:
    session = Session()
    try:
        user = session.query(BotParameters).filter_by(chat_id=str(chat_id)).first()
        if not user:
            user = BotParameters(chat_id=str(chat_id), username=username)
            session.add(user)
            session.commit()
        return {c.name: getattr(user, c.name) for c in user.__table__.columns}
    finally:
        session.close()

def update_user(chat_id: str, updates: Dict):
    session = Session()
    try:
        user = session.query(BotParameters).filter_by(chat_id=str(chat_id)).first()
        if user:
            for k, v in updates.items():
                setattr(user, k, v)
            session.commit()
    finally:
        session.close()

def toggle_kink(chat_id: str, kink_id: str) -> bool:
    session = Session()
    try:
        user = session.query(BotParameters).filter_by(chat_id=str(chat_id)).first()
        if user and hasattr(user, kink_id):
            current = getattr(user, kink_id)
            setattr(user, kink_id, not current)
            session.commit()
            return not current
        return None
    finally:
        session.close()

def log_task(chat_id: str, task: str, risk: int, status: str, photo: str = None, feedback: str = None):
    session = Session()
    try:
        session.add(TaskHistory(
            chat_id=str(chat_id),
            task_description=task,
            risk_level=risk,
            status=status,
            verification_photo_url=photo,
            feedback=feedback
        ))
        session.commit()
    finally:
        session.close()

def get_history(chat_id: str, limit: int = 10):
    session = Session()
    try:
        hist = session.query(TaskHistory).filter_by(chat_id=str(chat_id))\
            .order_by(TaskHistory.assigned_at.desc()).limit(limit).all()
        return [{'task': h.task_description, 'status': h.status, 'risk': h.risk_level} for h in hist]
    finally:
        session.close()

# ==================== AI TASK GENERATION ====================

def generate_task(user: Dict) -> str:
    """Generate task based on user preferences"""
    
    allowed = []
    disabled = []
    for k, v in KINK_CATEGORIES.items():
        if user.get(k, False):
            allowed.append(v)
        else:
            disabled.append(v)
    
    allowed_str = ", ".join(allowed) if allowed else "general domination"
    disabled_str = ", ".join(disabled[:5]) if disabled else "none"
    
    risk = user.get('risk_level', 3)
    creativity = user.get('creativity_level', 3)
    gender = user.get('avatar_gender', 'female')
    avatar_name = user.get('avatar_name', 'Mistress' if gender == 'female' else 'Master')
    
    risk_desc = {
        1: "Safe tasks at home only",
        2: "Low risk, minimal exposure",
        3: "Medium risk, possible semi-public elements",
        4: "High risk, public exposure likely",
        5: "EXTREME risk, dangerous exposure, possible social consequences"
    }.get(risk, "Medium risk")
    
    creativity_desc = {
        1: "Standard predictable tasks",
        2: "Some creativity",
        3: "Creative and varied",
        4: "Highly unpredictable",
        5: "Chaotic, bizarre, extreme creativity"
    }.get(creativity, "Creative")
    
    # Social media specific instruction
    social_enabled = user.get('social_media', False)
    social_instruction = ""
    if social_enabled and risk >= 4:
        social_instruction = "Social Media tasks allowed: posting exposed photos, risky DMs, public stories, etc."
    else:
        social_instruction = "NO social media tasks - keep offline only"
    
    prompt = f"""As {avatar_name} ({gender} dominant), generate a BDSM task.

RISK LEVEL {risk}/5: {risk_desc}
CREATIVITY LEVEL {creativity}/5: {creativity_desc}
{social_instruction}

ALLOWED: {allowed_str}
FORBIDDEN: {disabled_str}

RULES:
- Risk {risk}/5 means: {risk_desc}
- Creativity {creativity}/5 means: {creativity_desc}
- If marking forbidden: NO writing/drawing on body
- If social_media disabled: NO online posting, NO screenshots, NO DMs
- Task must be completable in 30 minutes
- Require photo proof

Generate ONE task:"""
    
    response = generate_ai(prompt, 300)
    if response:
        # Post-filter for social media
        if not user.get('social_media', False):
            social_words = ['post', 'posting', 'social media', 'instagram', 'twitter', 'snapchat', 
                          'story', 'dm', 'message', 'send to', 'upload', 'share online',
                          'facebook', 'reddit', 'tiktok', 'onlyfans', 'screenshot']
            if any(word in response.lower() for word in social_words):
                logger.warning("AI generated social media task without permission")
                return get_risky_fallback(user)
        
        # Filter marking
        if not user.get('marking', True):
            forbidden = ['write', 'writing', 'draw', 'drawing', 'marker', 'sharpie', 'lipstick', 'pen on']
            if any(f in response.lower() for f in forbidden):
                return get_risky_fallback(user)
        return response
    
    return get_risky_fallback(user)

def generate_ai(prompt: str, max_tokens: int = 300) -> str:
    if not VENVENICE_API_KEY:
        return None
    try:
        r = requests.post(
            "https://api.venice.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {VENVENICE_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": VENVENICE_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a dominant AI. Generate creative, risky BDSM tasks."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.9
            },
            timeout=30
        )
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
    except Exception as e:
        logger.error(f"AI error: {e}")
    return None

def get_risky_fallback(user: Dict) -> str:
    """Get fallback based on risk level and kinks"""
    risk = user.get('risk_level', 3)
    gender = user.get('avatar_gender', 'female')
    name = user.get('avatar_name', 'Mistress' if gender == 'female' else 'Master')
    social = user.get('social_media', False)
    
    tasks = {
        1: [
            f"{name} commands you to kneel and photograph your submission",
            f"Edge yourself once at {name}'s command, photo proof required",
            f"Write {name}'s name on paper and hold it while kneeling"
        ],
        2: [
            f"Take a photo in your underwear near a window",
            f"{name} demands you spank yourself 10 times and show results",
            f"Edge for 5 minutes then stop, photograph your frustration"
        ],
        3: [
            f"Go to your front door, drop pants for 10 seconds, photo proof",
            f"Take a risky photo in a semi-public bathroom",
            f"{name} demands you flash a window with lights on"
        ],
        4: [
            f"Walk to your mailbox nude at night, photo at the box",
            f"Take a photo in your car in a parking lot with shirt off",
            f"Go to a hotel hallway nude, quick photo before someone comes",
            f"Flash your car's headlights while exposed, photo proof"
        ],
        5: [
            f"Go to a 24hr store bathroom, leave door unlocked and exposed",
            f"Walk nude from your car to your door during day, video proof",
            f"Take photo in apartment hallway/stairwell nude",
            f"Go to laundry room nude while others might be there",
            f"Flash a delivery driver or passerby, describe their reaction",
            f"Take photo in front of window facing street during daytime"
        ]
    }
    
    pool = tasks.get(risk, tasks[3]).copy()
    
    # Add social media tasks if enabled and risk >= 4
    if social and risk >= 4:
        pool.extend([
            "Post a subtle exposed photo to your Instagram story, screenshot proof",
            "Send a risky photo to a random contact, screenshot their reaction",
            "Post 'feeling naughty' with exposed photo on Twitter, screenshot",
            "Add a exposed photo to your Snapchat story for 1 minute, screenshot",
            "Send exposed photo to ex or crush, show their reply",
            "Post on Reddit gonewild with your photo, show the post",
            "Change profile pic to exposed for 5 minutes, screenshot proof",
            "Send exposed photo to wrong person 'accidentally', show reaction"
        ])
    
    if user.get('blackmail', False) and risk >= 4:
        pool.extend([
            f"Give {name} blackmail material - photo with ID visible",
            "Photograph yourself exposed with personal item visible"
        ])
    
    if user.get('exposure_risk', False) and risk >= 4:
        pool.extend([
            "Leave blinds open while doing task, photo from outside view",
            "Stand nude in front of window facing street at night"
        ])
    
    return random.choice(pool)

def verify_photo(task: str, photo_url: str) -> tuple:
    prompt = f"""Task: {task}
Analyze photo - does it prove completion?
Format: VERDICT: YES/NO, REASON: explanation, COMMENT: dominant feedback"""
    
    result = generate_ai(prompt, 150)
    if result:
        yes = "VERDICT: YES" in result.upper()
        reason = ""
        comment = ""
        for line in result.split('\n'):
            if 'REASON:' in line:
                reason = line.split(':', 1)[1].strip()
            elif 'COMMENT:' in line:
                comment = line.split(':', 1)[1].strip()
        return yes, reason, comment or "Reviewed."
    return True, "", "Photo received."

# ==================== SCHEDULER ====================

async def scheduled_check(context: ContextTypes.DEFAULT_TYPE):
    """Send scheduled tasks"""
    session = Session()
    try:
        users = session.query(BotParameters).filter_by(scheduling_enabled=True).all()
        
        for u in users:
            # Skip if has pending task
            if u.current_task and not u.task_completed:
                continue
            
            # Check frequency
            if u.last_task_sent:
                mins = (datetime.utcnow() - u.last_task_sent).total_seconds() / 60
                if mins < u.task_frequency_minutes:
                    continue
            
            user_dict = {c.name: getattr(u, c.name) for c in u.__table__.columns}
            
            task_text = generate_task(user_dict)
            
            u.current_task = task_text
            u.task_assigned_at = datetime.utcnow()
            u.task_completed = False
            u.last_task_sent = datetime.utcnow()
            session.commit()
            
            try:
                name = u.avatar_name or 'Mistress'
                risk_emoji = "🔥" * u.risk_level
                
                keyboard = [[
                    InlineKeyboardButton("Complete", callback_data="complete_task"),
                    InlineKeyboardButton("Give Up", callback_data="give_up")
                ]]
                
                await context.bot.send_message(
                    chat_id=u.chat_id,
                    text=f"""{risk_emoji} *Scheduled Task from {name}*

{task_text}

⏰ Complete within 30 minutes or face punishment.""",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                asyncio.create_task(auto_expire(u.chat_id, 30, context))
                
            except Exception as e:
                logger.error(f"Failed to send to {u.chat_id}: {e}")
    finally:
        session.close()

async def auto_expire(chat_id: str, minutes: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(minutes * 60)
    
    user = get_user(chat_id)
    if user.get('current_task') and not user.get('task_completed'):
        log_task(chat_id, user['current_task'], user.get('risk_level', 3), 'expired')
        
        update_user(chat_id, {
            'total_tasks_failed': user['total_tasks_failed'] + 1,
            'current_streak': 0,
            'points': max(0, user['points'] - 10),
            'current_task': None,
            'task_completed': False
        })
        
        name = user.get('avatar_name', 'Mistress')
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ *Task Expired*\n\n{name} is disappointed. -10 points."
        )

# ==================== HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id, update.effective_user.username)
    
    await update.message.reply_text(
        f"""Welcome to DOM Bot v9.1

Your Chat ID: `{chat_id}`

🎭 */avatar* - Create your dominant (M/F/Trans)
⚙️ */setfrequency* - Task schedule
🔥 */risk* - Risk level (1-5)
🎨 */creativity* - Creativity level (1-5)
🚫 */limits* - Set kink limits (includes Social Media toggle)
📋 */task* - Get task now
📊 */status* - Your stats
🎁 */reward* - Nude rewards

Social Media Exposure is now a toggleable kink! Keep it OFF for safety."""
    )

async def avatar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = [
        [InlineKeyboardButton("👨 Male", callback_data="av_gender_male"),
         InlineKeyboardButton("👩 Female", callback_data="av_gender_female")],
        [InlineKeyboardButton("⚧ Trans", callback_data="av_gender_trans")],
        [InlineKeyboardButton("Customize Appearance", callback_data="av_custom")]
    ]
    
    await update.message.reply_text(
        "Select your dominant's gender:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def av_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    gender = query.data.replace("av_gender_", "")
    
    name = "Master" if gender == "male" else "Mistress" if gender == "female" else "Domme"
    
    update_user(chat_id, {
        'avatar_gender': gender,
        'avatar_name': name
    })
    
    await query.edit_message_text(
        f"✅ Gender set: {gender.title()}\n\nUse /avatar to customize appearance."
    )

async def av_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    gender = user.get('avatar_gender', 'female')
    
    keyboard = [
        [InlineKeyboardButton(f"Ethnicity: {user.get('avatar_ethnicity', 'white')}", 
                              callback_data="av_ethnicity")],
        [InlineKeyboardButton(f"Body: {user.get('avatar_body', 'curvy')}", 
                              callback_data="av_body")],
        [InlineKeyboardButton(f"Hair: {user.get('avatar_hair_color', 'blonde')}", 
                              callback_data="av_hair")],
        [InlineKeyboardButton(f"Pubic: {user.get('avatar_pubic', 'trimmed')}", 
                              callback_data="av_pubic")],
    ]
    
    if gender == 'female':
        keyboard.append([InlineKeyboardButton(
            f"Breasts: {user.get('avatar_feature_size', 'large')}", 
            callback_data="av_feature")])
    elif gender == 'male':
        keyboard.append([InlineKeyboardButton(
            f"Cock: {user.get('avatar_feature_size', 'large')}", 
            callback_data="av_feature")])
    else:
        keyboard.append([InlineKeyboardButton(
            f"Breasts/Cock: {user.get('avatar_feature_size', 'large')}", 
            callback_data="av_feature")])
    
    keyboard.append([InlineKeyboardButton(f"Mood: {user.get('avatar_mood', 'strict')}", 
                                          callback_data="av_mood")])
    keyboard.append([InlineKeyboardButton("Done", callback_data="av_done")])
    
    await query.edit_message_text(
        f"Customize your {gender} dominant:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cycle_option(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                     option: str, options: list):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    current = user.get(f'avatar_{option}', options[0])
    idx = options.index(current) if current in options else 0
    next_val = options[(idx + 1) % len(options)]
    
    update_user(chat_id, {f'avatar_{option}': next_val})
    await av_custom_callback(update, context)

async def av_ethnicity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_option(update, context, 'ethnicity', ETHNICITIES)

async def av_body_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_option(update, context, 'body', BODY_TYPES)

async def av_hair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_option(update, context, 'hair_color', HAIR_COLORS)

async def av_pubic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_option(update, context, 'pubic', PUBIC_STYLES)

async def av_feature_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    gender = user.get('avatar_gender', 'female')
    
    sizes = FEMALE_SIZES if gender in ['female', 'trans'] else MALE_SIZES
    await cycle_option(update, context, 'feature_size', sizes)

async def av_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moods = ['strict', 'playful', 'cruel', 'seductive', 'sadistic']
    await cycle_option(update, context, 'mood', moods)

async def av_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Avatar customized!")

async def setfrequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = [
        [InlineKeyboardButton("15 min", callback_data="freq_15"),
         InlineKeyboardButton("30 min", callback_data="freq_30")],
        [InlineKeyboardButton("1 hour", callback_data="freq_60"),
         InlineKeyboardButton("2 hours", callback_data="freq_120")],
        [InlineKeyboardButton("4 hours", callback_data="freq_240"),
         InlineKeyboardButton("8 hours", callback_data="freq_480")],
        [InlineKeyboardButton("Manual only", callback_data="freq_0")]
    ]
    
    await update.message.reply_text(
        "⏰ Set task frequency:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def freq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    mins = int(query.data.replace("freq_", ""))
    
    update_user(chat_id, {
        'task_frequency_minutes': mins,
        'scheduling_enabled': mins > 0
    })
    
    msg = f"Tasks every {mins} minutes" if mins > 0 else "Manual mode"
    await query.edit_message_text(f"✅ {msg}")

async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = []
    for level, desc in RISK_LEVELS.items():
        keyboard.append([InlineKeyboardButton(
            f"{level}: {desc}", 
            callback_data=f"risk_{level}"
        )])
    
    await update.message.reply_text(
        "🔥 Set risk level:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def risk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    level = int(query.data.replace("risk_", ""))
    
    update_user(chat_id, {'risk_level': level})
    await query.edit_message_text(f"✅ Risk level: {level}/5 - {RISK_LEVELS[level]}")

async def creativity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = []
    for level, desc in CREATIVITY_LEVELS.items():
        keyboard.append([InlineKeyboardButton(
            f"{level}: {desc}", 
            callback_data=f"creativity_{level}"
        )])
    
    await update.message.reply_text(
        "🎨 Set creativity level:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def creativity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    level = int(query.data.replace("creativity_", ""))
    
    update_user(chat_id, {'creativity_level': level})
    await query.edit_message_text(f"✅ Creativity: {level}/5")

async def limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    keyboard = []
    row = []
    
    for kink_id, kink_name in KINK_CATEGORIES.items():
        enabled = user.get(kink_id, True)
        emoji = "✅" if enabled else "❌"
        row.append(InlineKeyboardButton(
            f"{emoji} {kink_name}", 
            callback_data=f"toggle_{kink_id}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Done", callback_data="limits_done")])
    
    await update.message.reply_text(
        "Your Limits (click to toggle):\n"
        "📱 Social Media Exposure is OFF by default for safety",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    data = query.data
    
    if data == "limits_done":
        await query.edit_message_text("✅ Limits updated!")
        return
    
    kink_id = data.replace("toggle_", "")
    new_val = toggle_kink(chat_id, kink_id)
    
    # Refresh menu
    user = get_user(chat_id)
    keyboard = []
    row = []
    
    for kid, kname in KINK_CATEGORIES.items():
        enabled = user.get(kid, True)
        emoji = "✅" if enabled else "❌"
        row.append(InlineKeyboardButton(
            f"{emoji} {kname}", 
            callback_data=f"toggle_{kid}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Done", callback_data="limits_done")])
    
    status = "enabled" if new_val else "disabled"
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    # Check pending
    if user.get('current_task') and not user.get('task_completed'):
        await update.message.reply_text(
            f"You have a pending task:\n\n{user['current_task']}\n\nComplete it first!"
        )
        return
    
    task_text = generate_task(user)
    risk = user.get('risk_level', 3)
    
    update_user(chat_id, {
        'current_task': task_text,
        'task_assigned_at': datetime.utcnow(),
        'task_completed': False,
        'photo_retry_count': 0,
        'last_task_sent': datetime.utcnow()
    })
    
    keyboard = [[
        InlineKeyboardButton("Complete", callback_data="complete_task"),
        InlineKeyboardButton("Give Up", callback_data="give_up")
    ]]
    
    name = user.get('avatar_name', 'Mistress')
    risk_emoji = "🔥" * risk
    
    await update.message.reply_text(
        f"""{risk_emoji} *Task from {name}*

{task_text}

⏰ 30 minutes to complete.""",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    asyncio.create_task(auto_expire(chat_id, 30, context))

async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Send photo proof.")

async def give_up_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    log_task(chat_id, user.get('current_task', ''), user.get('risk_level', 3), 'failed')
    
    update_user(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'points': max(0, user['points'] - 5),
        'current_task': None
    })
    
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"{name} is disappointed. Task failed.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    if not user.get('current_task'):
        await update.message.reply_text("No active task.")
        return
    
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_url = file.file_path
    
    await update.message.reply_text(f"{name} is reviewing...")
    
    success, reason, comment = verify_photo(user['current_task'], photo_url)
    
    if success:
        new_completed = user['total_tasks_completed'] + 1
        new_streak = user['current_streak'] + 1
        new_points = user['points'] + (user.get('risk_level', 3) * 5)
        new_nude = user.get('tasks_since_nude', 0) + 1
        
        log_task(chat_id, user['current_task'], user.get('risk_level', 3), 
                'completed', photo_url, comment)
        
        update_user(chat_id, {
            'total_tasks_completed': new_completed,
            'current_streak': new_streak,
            'longest_streak': max(user['longest_streak'], new_streak),
            'points': new_points,
            'tasks_since_nude': new_nude,
            'current_task': None
        })
        
        nude_msg = ""
        if user.get('nude_reward_enabled', True) and new_nude >= user.get('nude_frequency', 3):
            nude_msg = f"\n\n🎁 Earned nude from {name}! Use /reward"
            update_user(chat_id, {'tasks_since_nude': 0})
        
        await update.message.reply_text(
            f"✅ Verified by {name}\n\n{comment}\n\n"
            f"Streak: {new_streak} | Points: {new_points}{nude_msg}"
        )
    else:
        retry = user.get('photo_retry_count', 0) + 1
        
        if retry >= 2:
            log_task(chat_id, user['current_task'], user.get('risk_level', 3),
                    'failed', feedback=reason)
            
            update_user(chat_id, {
                'total_tasks_failed': user['total_tasks_failed'] + 1,
                'current_streak': 0,
                'points': max(0, user['points'] - 10),
                'current_task': None,
                'photo_retry_count': 0
            })
            
            await update.message.reply_text(f"❌ Failed: {reason}")
        else:
            update_user(chat_id, {'photo_retry_count': retry})
            
            keyboard = [[
                InlineKeyboardButton("Try Again", callback_data="retry_photo"),
                InlineKeyboardButton("Give Up", callback_data="give_up_photo")
            ]]
            
            await update.message.reply_text(
                f"❌ {reason}\n\nTries left: {2 - retry}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def retry_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("Send better photo.")

async def give_up_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    log_task(chat_id, user.get('current_task', ''), user.get('risk_level', 3), 'failed')
    
    update_user(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'current_task': None
    })
    
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text(f"{name} is disappointed.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    current = ""
    if user.get('current_task'):
        current = f"\n🎯 Active: {user['current_task'][:100]}..."
    
    social_status = "ON" if user.get('social_media', False) else "OFF"
    
    await update.message.reply_text(
        f"""📊 {name}'s Pet

Completed: {user['total_tasks_completed']}
Failed: {user['total_tasks_failed']}
Streak: {user['current_streak']} (Best: {user['longest_streak']})
Points: {user['points']}

Risk: {user.get('risk_level', 3)}/5
Creativity: {user.get('creativity_level', 3)}/5
Frequency: {user.get('task_frequency_minutes', 60)}min
Social Media: {social_status}

Nude Progress: {user.get('tasks_since_nude', 0)}/{user.get('nude_frequency', 3)}
{current}"""
    )

async def reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    if not user.get('nude_reward_enabled', True):
        await update.message.reply_text("Nudes disabled.")
        return
    
    progress = user.get('tasks_since_nude', 0)
    needed = user.get('nude_frequency', 3)
    
    if progress >= needed:
        gender = user.get('avatar_gender', 'female')
        desc = f"{user.get('avatar_ethnicity')} {gender} with {user.get('avatar_hair_color')} hair"
        
        if gender == 'female':
            desc += f", {user.get('avatar_feature_size')} breasts"
        elif gender == 'male':
            desc += f", {user.get('avatar_feature_size')} cock"
        else:
            desc += f", {user.get('avatar_feature_size')} breasts and cock"
        
        desc += f", {user.get('avatar_body')} body, {user.get('avatar_pubic')} pubic hair"
        
        update_user(chat_id, {'tasks_since_nude': 0})
        
        await update.message.reply_text(
            f"""🎁 Nude from {name}

*Avatar:* {desc}
*Pose:* Dominant, {user.get('avatar_mood')} mood
*State:* Fully nude, exposing everything

[AI Image would generate]

"{name} says: You've earned this view, pet. Now get back to serving me." """
        )
    else:
        await update.message.reply_text(
            f"Progress: {progress}/{needed} tasks for nude reward"
        )

async def resetowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("YES DELETE ALL", callback_data="confirm_reset"),
        InlineKeyboardButton("Cancel", callback_data="cancel_reset")
    ]]
    await update.message.reply_text("⚠️ Delete ALL data?", reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    
    session = Session()
    try:
        session.query(BotParameters).filter_by(chat_id=str(chat_id)).delete()
        session.query(TaskHistory).filter_by(chat_id=str(chat_id)).delete()
        session.commit()
    finally:
        session.close()
    
    await update.callback_query.edit_message_text("All data deleted. Send /start")

async def cancel_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Cancelled.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ==================== MAIN ====================

def main():
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_TOKEN not set!")
    
    app = Application.builder().token(token).build()
    
    # Jobs
    job_queue = app.job_queue
    job_queue.run_repeating(scheduled_check, interval=60, first=10)
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("avatar", avatar))
    app.add_handler(CommandHandler("setfrequency", setfrequency))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(CommandHandler("creativity", creativity))
    app.add_handler(CommandHandler("limits", limits))
    app.add_handler(CommandHandler("task", task))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("reward", reward))
    app.add_handler(CommandHandler("resetowner", resetowner))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(av_gender_callback, pattern="^av_gender_"))
    app.add_handler(CallbackQueryHandler(av_custom_callback, pattern="^av_custom$"))
    app.add_handler(CallbackQueryHandler(av_ethnicity_callback, pattern="^av_ethnicity$"))
    app.add_handler(CallbackQueryHandler(av_body_callback, pattern="^av_body$"))
    app.add_handler(CallbackQueryHandler(av_hair_callback, pattern="^av_hair$"))
    app.add_handler(CallbackQueryHandler(av_pubic_callback, pattern="^av_pubic$"))
    app.add_handler(CallbackQueryHandler(av_feature_callback, pattern="^av_feature$"))
    app.add_handler(CallbackQueryHandler(av_mood_callback, pattern="^av_mood$"))
    app.add_handler(CallbackQueryHandler(av_done_callback, pattern="^av_done$"))
    app.add_handler(CallbackQueryHandler(freq_callback, pattern="^freq_"))
    app.add_handler(CallbackQueryHandler(risk_callback, pattern="^risk_"))
    app.add_handler(CallbackQueryHandler(creativity_callback, pattern="^creativity_"))
    app.add_handler(CallbackQueryHandler(toggle_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_task$"))
    app.add_handler(CallbackQueryHandler(give_up_callback, pattern="^give_up$"))
    app.add_handler(CallbackQueryHandler(retry_photo_callback, pattern="^retry_photo$"))
    app.add_handler(CallbackQueryHandler(give_up_photo_callback, pattern="^give_up_photo$"))
    app.add_handler(CallbackQueryHandler(confirm_reset, pattern="^confirm_reset$"))
    app.add_handler(CallbackQueryHandler(cancel_reset, pattern="^cancel_reset$"))
    
    # Messages
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(error_handler)
    
    logger.info("DOM Bot v9.1 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()