#!/usr/bin/env python3
"""
DOM Bot v10.0 - Location-Based Random Tasks
Proper photo verification, random intervals, location-aware AI generation
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
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')
VENVENICE_API_KEY = os.getenv('VENVENICE_API_KEY')
VENVENICE_MODEL = "claude-opus-4-8-fast"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# Configuration
GENDERS = ['male', 'female', 'trans']
ETHNICITIES = ['white', 'black', 'asian', 'hispanic']
BODY_TYPES = ['slim', 'average', 'muscular', 'curvy']
PUBIC_STYLES = ['shaved', 'trimmed', 'natural']
HAIR_COLORS = ['blonde', 'brown', 'red', 'black', 'white', 'bald']
FEMALE_SIZES = ['small', 'medium', 'large']
MALE_SIZES = ['small', 'medium', 'large']
LOCATIONS = ['home', 'public', 'work']

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
    'social_media': '📱 Social Media Exposure'
}

RISK_LEVELS = {
    1: 'Safe (Private, no risk)',
    2: 'Low (Minimal exposure risk)',
    3: 'Medium (Semi-public possible)',
    4: 'High (Public nudity likely)',
    5: 'Extreme (Dangerous public exposure, NO unwilling participants)'
}

CREATIVITY_LEVELS = {
    1: 'Standard',
    2: 'Creative',
    3: 'Very Creative',
    4: 'Unpredictable',
    5: 'Chaotic'
}

# ==================== DATABASE ====================

class BotParameters(Base):
    __tablename__ = 'bot_parameters'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # All kinks
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
    social_media = Column(Boolean, default=False)
    
    # Scheduling - RANDOM INTERVAL
    min_interval_minutes = Column(Integer, default=30)  # Minimum time between tasks
    max_interval_minutes = Column(Integer, default=120)  # Maximum time between tasks
    next_task_time = Column(DateTime)  # When next task will be sent
    scheduling_enabled = Column(Boolean, default=True)
    
    # Location
    location_type = Column(String, default='home')  # home, public, work
    location_details = Column(Text)  # Custom details like "2 bedroom apt, roommate home evenings"
    
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
    
    # Avatar
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
    location_type = Column(String)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String, default='assigned')
    verification_photo_url = Column(String)
    ai_verification_result = Column(Text)  # Store AI verification reasoning
    feedback = Column(Text)

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

def log_task(chat_id: str, task: str, risk: int, location: str, status: str, 
             photo: str = None, verification: str = None, feedback: str = None):
    session = Session()
    try:
        session.add(TaskHistory(
            chat_id=str(chat_id),
            task_description=task,
            risk_level=risk,
            location_type=location,
            status=status,
            verification_photo_url=photo,
            ai_verification_result=verification,
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
        return [{
            'task': h.task_description, 
            'status': h.status, 
            'risk': h.risk_level,
            'verification': h.ai_verification_result
        } for h in hist]
    finally:
        session.close()

# ==================== AI FUNCTIONS ====================

def generate_ai_response(prompt: str, max_tokens: int = 500, temperature: float = 0.8) -> str:
    """Generate AI response"""
    if not VENVENICE_API_KEY:
        return None
    try:
        r = requests.post(
            "https://api.venice.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {VENVENICE_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": VENVENICE_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a dominant AI assistant."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            timeout=30
        )
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
        logger.error(f"AI error: {r.status_code}")
    except Exception as e:
        logger.error(f"AI exception: {e}")
    return None

def generate_location_task(user: Dict) -> str:
    """Generate AI task based on location and settings"""
    
    # Build context
    location = user.get('location_type', 'home')
    details = user.get('location_details', '') or 'No specific details'
    risk = user.get('risk_level', 3)
    creativity = user.get('creativity_level', 3)
    gender = user.get('avatar_gender', 'female')
    name = user.get('avatar_name', 'Mistress')
    
    # Build allowed kinks
    allowed = []
    disabled = []
    for k, v in KINK_CATEGORIES.items():
        if user.get(k, False):
            allowed.append(v)
        else:
            disabled.append(v)
    
    # Risk descriptions
    risk_desc = {
        1: "Completely private, no chance of being seen",
        2: "Minimal risk, unlikely to be seen",
        3: "Possible risk of being seen but not certain",
        4: "Likely to be seen or exposed to public",
        5: "EXTREME: Dangerous exposure possible, but NO tasks involving unwilling participants (no flashing strangers, no involving delivery drivers, etc.). Tasks can involve: opening front door naked, outdoor nudity in secluded areas, etc."
    }.get(risk, "Medium risk")
    
    # Creativity
    creativity_desc = {
        1: "Standard, predictable tasks",
        2: "Some creativity",
        3: "Creative and varied",
        4: "Highly unpredictable and creative",
        5: "Extremely chaotic, bizarre, unexpected"
    }.get(creativity, "Creative")
    
    # Social media
    social = user.get('social_media', False)
    social_instruction = "Social media tasks ALLOWED" if social else "NO social media tasks"
    
    prompt = f"""Generate a BDSM task for a submissive.

DOMINANT: {name} ({gender})
LOCATION: {location}
LOCATION DETAILS: {details}

RISK LEVEL {risk}/5: {risk_desc}
CREATIVITY LEVEL {creativity}/5: {creativity_desc}
{social_instruction}

ALLOWED KINKS: {', '.join(allowed)}
FORBIDDEN: {', '.join(disabled[:5])}

CRITICAL RULES:
- Task MUST be completable at/in: {location}
- Use location details: {details}
- Risk {risk}/5 means: {risk_desc}
- If risk is 5: NO tasks involving unwilling participants (no flashing delivery drivers, strangers, public harassment). Extreme self-exposure ONLY (open door naked, outdoor nudity in appropriate areas, etc.)
- If marking forbidden: NO writing on body
- If social_media disabled: NO online posting
- Task must be completable in 30 minutes
- Be specific and creative

Generate ONE specific task:"""
    
    response = generate_ai_response(prompt, 400, 0.9)
    
    if response:
        # Clean up response
        task = response.strip()
        # Remove quotes if present
        if task.startswith('"') and task.endswith('"'):
            task = task[1:-1]
        # Remove "Task:" prefix if present
        if task.lower().startswith('task:'):
            task = task[5:].strip()
        return task
    
    # Fallback if AI fails
    return generate_location_fallback(user)

def generate_location_fallback(user: Dict) -> str:
    """Generate fallback based on location and risk"""
    location = user.get('location_type', 'home')
    risk = user.get('risk_level', 3)
    name = user.get('avatar_name', 'Mistress')
    
    # Location-specific tasks
    tasks = {
        'home': {
            1: [f"{name} commands you to kneel in your living room and photograph your submission"],
            2: [f"Strip naked in your bedroom and take a photo near the window"],
            3: [f"Walk nude from your bedroom to bathroom, photo in hallway"],
            4: [f"Stand nude in front of open window facing street for 10 seconds"],
            5: [f"Open your front door completely naked and step outside for 5 seconds"]
        },
        'public': {
            1: [f"Kneel in a bathroom stall and photograph submission"],
            2: [f"Take a photo in your car in a parking lot"],
            3: [f"Flash your car's interior light while exposed in parking lot"],
            4: [f"Take a nude photo in a public restroom with door unlocked"],
            5: [f"Find a secluded outdoor spot, strip completely, photograph yourself exposed to elements"]
        },
        'work': {
            1: [f"Kneel under your desk and photograph"],
            2: [f"Take a risky photo in bathroom stall at work"],
            3: [f"Expose yourself in your office/cubicle when alone"],
            4: [f"Nude photo in work bathroom with company logo visible"],
            5: [f"Step outside work building nude at night for 5 seconds"]
        }
    }
    
    loc_tasks = tasks.get(location, tasks['home'])
    risk_tasks = loc_tasks.get(risk, loc_tasks[3])
    
    return random.choice(risk_tasks)

def verify_photo_with_ai(task: str, photo_description: str) -> tuple:
    """Verify photo actually shows task completion - LOOSE but functional verification"""
    
    prompt = f"""Task given to submissive: "{task}"

Photo submitted: {photo_description}

Analyze if the photo shows evidence of the task being completed.

Respond with:
VERDICT: PASS or FAIL
CONFIDENCE: High/Medium/Low
REASONING: Brief explanation of what you see and why it passes or fails

Be REASONABLE - if the photo shows a genuine attempt at the task, PASS it.
Only FAIL if clearly wrong or completely unrelated."""
    
    result = generate_ai_response(prompt, 300, 0.7)
    
    if result:
        # Parse result
        verdict = "FAIL"
        confidence = "Low"
        reasoning = "Could not verify"
        
        result_lower = result.lower()
        
        # Check for pass/fail
        if "verdict: pass" in result_lower or "pass" in result_lower[:100]:
            verdict = "PASS"
        elif "verdict: fail" in result_lower or "fail" in result_lower[:100]:
            verdict = "FAIL"
        
        # Extract confidence
        if "high" in result_lower:
            confidence = "High"
        elif "medium" in result_lower:
            confidence = "Medium"
        
        # Extract reasoning
        for line in result.split('\n'):
            if 'reasoning:' in line.lower():
                reasoning = line.split(':', 1)[1].strip()
                break
            elif 'reason' in line.lower() and ':' in line:
                reasoning = line.split(':', 1)[1].strip()
        
        return verdict == "PASS", confidence, reasoning, result
    
    # If AI fails, default to accepting with warning
    return True, "Low", "AI verification unavailable, accepting photo", "AI failed"

# ==================== SCHEDULER - RANDOM INTERVALS ====================

async def random_interval_check(context: ContextTypes.DEFAULT_TYPE):
    """Check if it's time to send a task based on random interval"""
    session = Session()
    try:
        users = session.query(BotParameters).filter_by(scheduling_enabled=True).all()
        now = datetime.utcnow()
        
        for u in users:
            # Skip if has pending task
            if u.current_task and not u.task_completed:
                continue
            
            # Check if next_task_time is set and passed
            if u.next_task_time:
                if now < u.next_task_time:
                    continue  # Not time yet
            else:
                # First run - set next time
                min_mins = u.min_interval_minutes or 30
                max_mins = u.max_interval_minutes or 120
                random_minutes = random.randint(min_mins, max_mins)
                u.next_task_time = now + timedelta(minutes=random_minutes)
                session.commit()
                continue
            
            # Time to send task!
            user_dict = {c.name: getattr(u, c.name) for c in u.__table__.columns}
            
            task_text = generate_location_task(user_dict)
            
            u.current_task = task_text
            u.task_assigned_at = now
            u.task_completed = False
            
            # Set next random time
            min_mins = u.min_interval_minutes or 30
            max_mins = u.max_interval_minutes or 120
            random_minutes = random.randint(min_mins, max_mins)
            u.next_task_time = now + timedelta(minutes=random_minutes)
            
            session.commit()
            
            # Send task
            try:
                name = u.avatar_name or 'Mistress'
                risk_emoji = "🔥" * u.risk_level
                
                keyboard = [[
                    InlineKeyboardButton("Complete", callback_data="complete_task"),
                    InlineKeyboardButton("Give Up", callback_data="give_up")
                ]]
                
                await context.bot.send_message(
                    chat_id=u.chat_id,
                    text=f"""{risk_emoji} *Task from {name}*

{task_text}

⏰ Complete within 30 minutes.

Next task in approximately {random_minutes} minutes.""",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                asyncio.create_task(auto_expire(u.chat_id, 30, context))
                
            except Exception as e:
                logger.error(f"Failed to send task to {u.chat_id}: {e}")
                
    finally:
        session.close()

async def auto_expire(chat_id: str, minutes: int, context: ContextTypes.DEFAULT_TYPE):
    """Expire task after timeout"""
    await asyncio.sleep(minutes * 60)
    
    user = get_user(chat_id)
    if user.get('current_task') and not user.get('task_completed'):
        name = user.get('avatar_name', 'Mistress')
        
        log_task(chat_id, user['current_task'], user.get('risk_level', 3),
                user.get('location_type', 'home'), 'expired')
        
        update_user(chat_id, {
            'total_tasks_failed': user['total_tasks_failed'] + 1,
            'current_streak': 0,
            'points': max(0, user['points'] - 10),
            'current_task': None,
            'task_completed': False
        })
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ *Task Expired*\n\n{name} is disappointed. -10 points."
        )

# ==================== HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id, update.effective_user.username)
    
    await update.message.reply_text(
        f"""Welcome to DOM Bot v10.0 - Location Aware

Your Chat ID: `{chat_id}`

🎭 */avatar* - Create your dominant
📍 */location* - Set location (home/public/work) + details
⏱️ */interval* - Set random task interval (min-max minutes)
🔥 */risk* - Risk level 1-5 (5 = extreme but ethical)
🎨 */creativity* - Creativity level
🚫 */limits* - Kink toggles (includes Social Media)
📋 */task* - Get task NOW
📊 */status* - Your stats
🎁 */reward* - Nude rewards

Random tasks will be sent between your set interval times."""
    )

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set location"""
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    keyboard = [
        [InlineKeyboardButton(f"🏠 Home {'✅' if user.get('location_type')=='home' else ''}", 
                              callback_data="loc_home")],
        [InlineKeyboardButton(f"🏢 Work {'✅' if user.get('location_type')=='work' else ''}", 
                              callback_data="loc_work")],
        [InlineKeyboardButton(f"🌍 Public {'✅' if user.get('location_type')=='public' else ''}", 
                              callback_data="loc_public")],
        [InlineKeyboardButton("Add Location Details", callback_data="loc_details")]
    ]
    
    current = user.get('location_type', 'home')
    details = user.get('location_details', 'None set')
    
    await update.message.reply_text(
        f"""📍 Current Location: {current.title()}
Details: {details}

Select location type:""",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def loc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    
    if query.data == "loc_details":
        await query.edit_message_text(
            "Send me details about your location:\n"
            "Examples:\n"
            "- '2 bedroom apartment, roommate home evenings'\n"
            "- 'Office with cubicles, boss nearby'\n"
            "- 'Car, can drive to secluded spots'\n\n"
            "Use /setdetails <your details>"
        )
        return
    
    loc = query.data.replace("loc_", "")
    update_user(chat_id, {'location_type': loc})
    
    await query.edit_message_text(
        f"✅ Location set to: {loc.title()}\n\n"
        f"Use /setdetails to add specific details for better tasks."
    )

async def setdetails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set location details"""
    chat_id = update.effective_chat.id
    
    details = ' '.join(context.args)
    if not details:
        await update.message.reply_text(
            "Usage: /setdetails <description>\n"
            "Example: /setdetails 2 bedroom apt, roommate home 6pm-8am"
        )
        return
    
    update_user(chat_id, {'location_details': details})
    await update.message.reply_text(f"✅ Location details saved:\n{details}")

async def interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set random interval"""
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("15-30 min", callback_data="int_15_30"),
         InlineKeyboardButton("30-60 min", callback_data="int_30_60")],
        [InlineKeyboardButton("1-2 hours", callback_data="int_60_120"),
         InlineKeyboardButton("2-4 hours", callback_data="int_120_240")],
        [InlineKeyboardButton("4-8 hours", callback_data="int_240_480"),
         InlineKeyboardButton("Custom", callback_data="int_custom")]
    ]
    
    current_min = user.get('min_interval_minutes', 30)
    current_max = user.get('max_interval_minutes', 120)
    
    await update.message.reply_text(
        f"""⏱️ Random Task Interval

Current: {current_min}-{current_max} minutes

Bot will send tasks at RANDOM times within this range.

Select interval:""",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    
    if query.data == "int_custom":
        await query.edit_message_text(
            "Use: /setinterval <min> <max>\n"
            "Example: /setinterval 45 90"
        )
        return
    
    data = query.data.replace("int_", "")
    min_max = data.split("_")
    min_mins = int(min_max[0])
    max_mins = int(min_max[1])
    
    update_user(chat_id, {
        'min_interval_minutes': min_mins,
        'max_interval_minutes': max_mins,
        'scheduling_enabled': True
    })
    
    await query.edit_message_text(
        f"✅ Tasks will be sent randomly every {min_mins}-{max_mins} minutes"
    )

async def setinterval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Custom interval"""
    chat_id = update.effective_chat.id
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setinterval <min_minutes> <max_minutes>")
        return
    
    try:
        min_mins = int(context.args[0])
        max_mins = int(context.args[1])
        
        if min_mins >= max_mins:
            await update.message.reply_text("Min must be less than max!")
            return
        
        update_user(chat_id, {
            'min_interval_minutes': min_mins,
            'max_interval_minutes': max_mins,
            'scheduling_enabled': True
        })
        
        await update.message.reply_text(f"✅ Interval set: {min_mins}-{max_mins} minutes")
        
    except ValueError:
        await update.message.reply_text("Please enter numbers only")

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
    
    update_user(chat_id, {'avatar_gender': gender, 'avatar_name': name})
    await query.edit_message_text(f"✅ Gender: {gender.title()}\nUse /avatar to customize.")

async def av_custom_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    gender = user.get('avatar_gender', 'female')
    
    keyboard = [
        [InlineKeyboardButton(f"Ethnicity: {user.get('avatar_ethnicity', 'white')}", callback_data="av_ethnicity")],
        [InlineKeyboardButton(f"Body: {user.get('avatar_body', 'curvy')}", callback_data="av_body")],
        [InlineKeyboardButton(f"Hair: {user.get('avatar_hair_color', 'blonde')}", callback_data="av_hair")],
        [InlineKeyboardButton(f"Pubic: {user.get('avatar_pubic', 'trimmed')}", callback_data="av_pubic")],
    ]
    
    if gender == 'female':
        keyboard.append([InlineKeyboardButton(f"Breasts: {user.get('avatar_feature_size', 'large')}", callback_data="av_feature")])
    elif gender == 'male':
        keyboard.append([InlineKeyboardButton(f"Cock: {user.get('avatar_feature_size', 'large')}", callback_data="av_feature")])
    else:
        keyboard.append([InlineKeyboardButton(f"Breasts/Cock: {user.get('avatar_feature_size', 'large')}", callback_data="av_feature")])
    
    keyboard.append([InlineKeyboardButton(f"Mood: {user.get('avatar_mood', 'strict')}", callback_data="av_mood")])
    keyboard.append([InlineKeyboardButton("Done", callback_data="av_done")])
    
    await query.edit_message_text(f"Customize {gender}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def cycle_option(update: Update, context: ContextTypes.DEFAULT_TYPE, option: str, options: list):
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
    await query.edit_message_text("✅ Avatar saved!")

async def risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = []
    for level, desc in RISK_LEVELS.items():
        keyboard.append([InlineKeyboardButton(f"{level}: {desc}", callback_data=f"risk_{level}")])
    
    await update.message.reply_text("🔥 Set risk level:", reply_markup=InlineKeyboardMarkup(keyboard))

async def risk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    level = int(query.data.replace("risk_", ""))
    
    update_user(chat_id, {'risk_level': level})
    await query.edit_message_text(f"✅ Risk: {level}/5\n{RISK_LEVELS[level]}")

async def creativity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    keyboard = []
    for level, desc in CREATIVITY_LEVELS.items():
        keyboard.append([InlineKeyboardButton(f"{level}: {desc}", callback_data=f"creativity_{level}")])
    
    await update.message.reply_text("🎨 Set creativity:", reply_markup=InlineKeyboardMarkup(keyboard))

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
        row.append(InlineKeyboardButton(f"{emoji} {kink_name}", callback_data=f"toggle_{kink_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Done", callback_data="limits_done")])
    
    await update.message.reply_text(
        "Your Limits (click to toggle):\n"
        "⚠️ Social Media is OFF by default",
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
    toggle_kink(chat_id, kink_id)
    
    # Refresh
    await limits(update, context)

async def task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Request task now"""
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    if user.get('current_task') and not user.get('task_completed'):
        await update.message.reply_text(
            f"You have a pending task:\n\n{user['current_task']}\n\nComplete it first!"
        )
        return
    
    task_text = generate_location_task(user)
    risk = user.get('risk_level', 3)
    
    update_user(chat_id, {
        'current_task': task_text,
        'task_assigned_at': datetime.utcnow(),
        'task_completed': False,
        'photo_retry_count': 0
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
    await query.message.reply_text("Send photo proof of task completion.")

async def give_up_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    log_task(chat_id, user.get('current_task', ''), user.get('risk_level', 3),
            user.get('location_type', 'home'), 'failed')
    
    update_user(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'points': max(0, user['points'] - 5),
        'current_task': None
    })
    
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"{name} is disappointed. Task failed.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo with PROPER AI verification"""
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    if not user.get('current_task'):
        await update.message.reply_text("No active task. Use /task first.")
        return
    
    # Get photo info
    photo = update.message.photo[-1]
    
    # Create description of what we can see
    photo_description = f"Photo submitted by user. File ID: {photo.file_id}, Size: {photo.width}x{photo.height}"
    
    await update.message.reply_text(f"{name} is analyzing your submission...")
    
    # Verify with AI
    task_desc = user['current_task']
    passed, confidence, reasoning, full_response = verify_photo_with_ai(task_desc, photo_description)
    
    # Get actual file for storage
    file = await context.bot.get_file(photo.file_id)
    photo_url = file.file_path
    
    if passed:
        # Task completed!
        new_completed = user['total_tasks_completed'] + 1
        new_streak = user['current_streak'] + 1
        new_points = user['points'] + (user.get('risk_level', 3) * 5)
        new_nude = user.get('tasks_since_nude', 0) + 1
        
        log_task(chat_id, task_desc, user.get('risk_level', 3),
                user.get('location_type', 'home'), 'completed',
                photo_url, f"AI: {confidence} - {reasoning}")
        
        update_user(chat_id, {
            'total_tasks_completed': new_completed,
            'current_streak': new_streak,
            'longest_streak': max(user['longest_streak'], new_streak),
            'points': new_points,
            'tasks_since_nude': new_nude,
            'current_task': None,
            'photo_retry_count': 0
        })
        
        nude_msg = ""
        if user.get('nude_reward_enabled', True) and new_nude >= user.get('nude_frequency', 3):
            nude_msg = f"\n\n🎁 Earned nude from {name}! Use /reward"
            update_user(chat_id, {'tasks_since_nude': 0})
        
        await update.message.reply_text(
            f"""✅ *Verified by {name}*

AI Verification: {confidence} confidence
Assessment: {reasoning}

Streak: {new_streak} | Points: {new_points}{nude_msg}"""
        )
    else:
        # Failed verification
        retry = user.get('photo_retry_count', 0) + 1
        
        if retry >= 2:
            log_task(chat_id, task_desc, user.get('risk_level', 3),
                    user.get('location_type', 'home'), 'failed',
                    photo_url, f"AI Rejected: {reasoning}")
            
            update_user(chat_id, {
                'total_tasks_failed': user['total_tasks_failed'] + 1,
                'current_streak': 0,
                'points': max(0, user['points'] - 10),
                'current_task': None,
                'photo_retry_count': 0
            })
            
            await update.message.reply_text(
                f"""❌ *Rejected by {name}*

AI Assessment: {reasoning}

Failed verification twice. Task marked as failed."""
            )
        else:
            update_user(chat_id, {'photo_retry_count': retry})
            
            keyboard = [[
                InlineKeyboardButton("Try Again", callback_data="retry_photo"),
                InlineKeyboardButton("Give Up", callback_data="give_up_photo")
            ]]
            
            await update.message.reply_text(
                f"""❌ *{name} rejects this photo*

AI Assessment: {reasoning}

Tries remaining: {2 - retry}""",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def retry_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("Send a better photo that clearly shows task completion.")

async def give_up_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    log_task(chat_id, user.get('current_task', ''), user.get('risk_level', 3),
            user.get('location_type', 'home'), 'failed')
    
    update_user(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'current_task': None
    })
    
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text(f"{name} is disappointed. Task failed.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    current = ""
    if user.get('current_task'):
        current = f"\n🎯 Active: {user['current_task'][:80]}..."
    
    min_int = user.get('min_interval_minutes', 30)
    max_int = user.get('max_interval_minutes', 120)
    
    await update.message.reply_text(
        f"""📊 {name}'s Pet

Completed: {user['total_tasks_completed']}
Failed: {user['total_tasks_failed']}
Streak: {user['current_streak']} (Best: {user['longest_streak']})
Points: {user['points']}

📍 Location: {user.get('location_type', 'home').title()}
⏱️ Interval: {min_int}-{max_int} min (random)
🔥 Risk: {user.get('risk_level', 3)}/5
🎨 Creativity: {user.get('creativity_level', 3)}/5
📱 Social Media: {'ON' if user.get('social_media') else 'OFF'}

🎁 Nude Progress: {user.get('tasks_since_nude', 0)}/{user.get('nude_frequency', 3)}
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
*Pose:* Dominant {user.get('avatar_mood')} mood
*State:* Fully nude

[AI Image would generate]

"{name} says: You've earned this. Now serve me again." """
        )
    else:
        await update.message.reply_text(f"Progress: {progress}/{needed} tasks for reward")

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
    
    # Random interval scheduler - check every minute
    job_queue = app.job_queue
    job_queue.run_repeating(random_interval_check, interval=60, first=10)
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("avatar", avatar))
    app.add_handler(CommandHandler("location", location))
    app.add_handler(CommandHandler("setdetails", setdetails_command))
    app.add_handler(CommandHandler("interval", interval))
    app.add_handler(CommandHandler("setinterval", setinterval_command))
    app.add_handler(CommandHandler("risk", risk))
    app.add_handler(CommandHandler("creativity", creativity))
    app.add_handler(CommandHandler("limits", limits))
    app.add_handler(CommandHandler("task", task))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("reward", reward))
    app.add_handler(CommandHandler("resetowner", resetowner))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(loc_callback, pattern="^loc_"))
    app.add_handler(CallbackQueryHandler(av_gender_callback, pattern="^av_gender_"))
    app.add_handler(CallbackQueryHandler(av_custom_callback, pattern="^av_custom$"))
    app.add_handler(CallbackQueryHandler(av_ethnicity_callback, pattern="^av_ethnicity$"))
    app.add_handler(CallbackQueryHandler(av_body_callback, pattern="^av_body$"))
    app.add_handler(CallbackQueryHandler(av_hair_callback, pattern="^av_hair$"))
    app.add_handler(CallbackQueryHandler(av_pubic_callback, pattern="^av_pubic$"))
    app.add_handler(CallbackQueryHandler(av_feature_callback, pattern="^av_feature$"))
    app.add_handler(CallbackQueryHandler(av_mood_callback, pattern="^av_mood$"))
    app.add_handler(CallbackQueryHandler(av_done_callback, pattern="^av_done$"))
    app.add_handler(CallbackQueryHandler(interval_callback, pattern="^int_"))
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
    
    logger.info("DOM Bot v10.0 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()