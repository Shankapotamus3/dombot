#!/usr/bin/env python3
"""
DOM Bot v10.3 - Complete with Rewards & Avatar Images
Fixed variables, working photo verification, sporadic dominating images
"""

import os
import logging
import asyncio
import random
import io
import base64
import re
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration - FIXED VARIABLE NAMES
DATABASE_URL = os.getenv('DATABASE_URL')
VENICE_API_KEY = os.getenv('VENICE_API_KEY')
VENICE_API_URL = "https://api.venice.ai/api/v1/chat/completions"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set!")
if not VENICE_API_KEY:
    raise ValueError("VENICE_API_KEY not set!")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set!")

logger.info(f"API Key present: {bool(VENICE_API_KEY)}")
logger.info(f"Database present: {bool(DATABASE_URL)}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# ==================== CONFIGURATION ====================

GENDERS = ['male', 'female', 'trans']
ETHNICITIES = ['white', 'black', 'asian', 'hispanic']
BODY_TYPES = ['slim', 'average', 'muscular', 'curvy']
PUBIC_STYLES = ['shaved', 'trimmed', 'natural']
HAIR_COLORS = ['blonde', 'brown', 'red', 'black', 'white', 'bald']
FEMALE_SIZES = ['small', 'medium', 'large']
MALE_SIZES = ['small', 'medium', 'large']

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
    1: 'Safe (Private)',
    2: 'Low (Minimal risk)',
    3: 'Medium (Semi-public)',
    4: 'High (Public likely)',
    5: 'Extreme (Dangerous, ethical only - no unwilling participants)'
}

# Avatar moods for sporadic images
AVATAR_MOODS = {
    'commanding': {'desc': 'standing tall, arms crossed, intense eye contact', 'clothing': 'tight briefs or jockstrap, harness'},
    'pleased': {'desc': 'confident smile, relaxed posture', 'clothing': 'unbuttoned shirt, briefs'},
    'disappointed': {'desc': 'crossed arms, head tilted, looking down', 'clothing': 'formal wear or leather'},
    'angry': {'desc': 'fists clenched, leaning forward', 'clothing': 'sweat-soaked tank or bare chest'},
    'seductive': {'desc': 'reclining, inviting but dominant', 'clothing': 'minimal - briefs'},
    'dominant': {'desc': 'standing over, power pose', 'clothing': 'leather harness, boots'},
    'workout': {'desc': 'sweaty post-workout, muscles pumped', 'clothing': 'tight compression shorts'},
    'cruel': {'desc': 'towering angle, mocking smirk', 'clothing': 'full leather'},
    'inspecting': {'desc': 'examining intently', 'clothing': 'robe partially open'},
}

TASK_CATEGORIES = {
    'exposure': ['naked', 'strip', 'undress', 'bare', 'expose', 'display'],
    'position': ['kneel', 'bend', 'position', 'pose', 'present', 'assume'],
    'service': ['clean', 'prepare', 'arrange', 'service', 'organize'],
    'degradation': ['write', 'mark', 'label', 'admit', 'confess'],
    'edging': ['edge', 'stroke', 'touch', 'arouse', 'deny'],
    'public_risk': ['public', 'outside', 'visible', 'window', 'balcony', 'door'],
    'humiliation': ['embarrass', 'shame', 'humiliate', 'demean'],
    'physical': ['hold', 'maintain', 'endure', 'suffer', 'challenge'],
}

# ==================== DATABASE MODELS ====================

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
    
    # Random interval scheduling
    min_interval_minutes = Column(Integer, default=30)
    max_interval_minutes = Column(Integer, default=120)
    next_task_time = Column(DateTime)
    scheduling_enabled = Column(Boolean, default=True)
    
    # Location
    location_type = Column(String, default='home')
    location_details = Column(Text)
    
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
    recent_task_hashes = Column(Text, default='')
    
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
    
    # Rewards & avatar frequency
    nude_reward_enabled = Column(Boolean, default=True)
    nude_frequency = Column(Integer, default=3)
    tasks_since_nude = Column(Integer, default=0)
    avatar_frequency = Column(Float, default=0.3)  # 30% chance of avatar image with task

class TaskHistory(Base):
    __tablename__ = 'task_history'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, nullable=False)
    task_description = Column(Text, nullable=False)
    task_hash = Column(String)
    risk_level = Column(Integer, default=3)
    location_type = Column(String)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String, default='assigned')
    verification_photo_url = Column(String)
    ai_verification_result = Column(Text)
    ai_analysis = Column(Text)
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
            logger.info(f"Created new user: {chat_id}")
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

def log_task(chat_id: str, task: str, task_hash: str, risk: int, location: str, 
             status: str, photo: str = None, verification: str = None, analysis: str = None):
    session = Session()
    try:
        session.add(TaskHistory(
            chat_id=str(chat_id),
            task_description=task,
            task_hash=task_hash,
            risk_level=risk,
            location_type=location,
            status=status,
            verification_photo_url=photo,
            ai_verification_result=verification,
            ai_analysis=analysis
        ))
        session.commit()
    finally:
        session.close()

def get_recent_hashes(chat_id: str, hours: int = 48) -> Set[str]:
    session = Session()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent = session.query(TaskHistory).filter(
            TaskHistory.chat_id == str(chat_id),
            TaskHistory.assigned_at > cutoff
        ).all()
        return {t.task_hash for t in recent if t.task_hash}
    finally:
        session.close()

def get_history(chat_id: str, limit: int = 10):
    session = Session()
    try:
        hist = session.query(TaskHistory).filter_by(chat_id=str(chat_id))\
            .order_by(desc(TaskHistory.assigned_at)).limit(limit).all()
        return [{
            'task': h.task_description, 
            'status': h.status, 
            'risk': h.risk_level,
            'verification': h.ai_verification_result,
            'analysis': h.ai_analysis
        } for h in hist]
    finally:
        session.close()

def get_task_hash(description: str) -> str:
    normalized = re.sub(r'\d+', 'NUM', description.lower().strip())
    normalized = re.sub(r'[^\w\s]', '', normalized)
    return hashlib.md5(normalized.encode()).hexdigest()[:16]

# ==================== AI FUNCTIONS ====================

def generate_ai_response(prompt: str, max_tokens: int = 500, temperature: float = 0.8) -> Optional[str]:
    try:
        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": [
                    {"role": "system", "content": "You are a dominant AI assistant."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        else:
            logger.error(f"AI API error: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"AI request failed: {e}")
        return None

async def verify_photo_with_ai(task_description: str, photo_bytes: bytes) -> dict:
    try:
        photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
        
        prompt = f"""Verify BDSM task completion from selfie.

Task: "{task_description}"

ANALYZE:
1. Does photo show requested nudity/exposure?
2. Is position/pose correct? (selfies have limited angles)
3. Can you see arm/hand holding phone?
4. Does setting match task?
5. Evidence of compliance?

Format:
VERDICT: [VERIFIED or FAILED]
CONFIDENCE: [high/medium/low]
ANALYSIS: [explanation]

Be fair - selfies are harder to pose."""

        response = requests.post(
            VENICE_API_URL,
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{photo_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 400,
                "temperature": 0.2
            },
            timeout=60
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
            
            reasoning = ""
            for line in analysis.split('\n'):
                if 'analysis:' in line.lower():
                    reasoning = line.split(':', 1)[1].strip()
                    break
            
            return {
                "verified": is_verified,
                "confidence": confidence,
                "reasoning": reasoning or analysis[:200],
                "full_analysis": analysis
            }
        else:
            logger.error(f"Vision API error: {response.status_code}")
            return {
                "verified": True,
                "confidence": "low",
                "reasoning": "AI verification unavailable",
                "full_analysis": "API error"
            }
            
    except Exception as e:
        logger.error(f"Photo verification error: {e}")
        return {
            "verified": True,
            "confidence": "low",
            "reasoning": f"Error: {str(e)[:100]}",
            "full_analysis": str(e)
        }

def generate_avatar_image(user: Dict, mood_key: str, nude: bool = False) -> Optional[bytes]:
    """Generate avatar image - can be clothed (dominating) or nude (reward)"""
    try:
        gender = user.get('avatar_gender', 'female')
        ethnicity = user.get('avatar_ethnicity', 'white')
        body = user.get('avatar_body', 'curvy')
        hair = user.get('avatar_hair_color', 'blonde')
        feature = user.get('avatar_feature_size', 'large')
        pubic = user.get('avatar_pubic', 'trimmed')
        
        # Build physical description
        if gender == 'female':
            physical = f"{ethnicity} woman, {body} build, {hair} hair, {feature} breasts"
        elif gender == 'male':
            physical = f"{ethnicity} man, {body} build, {hair} hair, muscular"
        else:
            physical = f"{ethnicity} trans woman, {body} build, {hair} hair, {feature} breasts"
        
        # Mood/posing
        if nude:
            pose = "fully nude, explicit, dominant pose, confident"
            clothing = f"{pubic} pubic hair visible"
        else:
            mood_data = AVATAR_MOODS.get(mood_key, AVATAR_MOODS['commanding'])
            pose = mood_data['desc']
            clothing = mood_data['clothing']
        
        prompt = f"Professional photograph of dominant {physical}, {pose}, {clothing if not nude else 'fully nude, explicit content'}, high quality, detailed skin, professional lighting, 4k, dominant energy"
        
        response = requests.post(
            VENICE_IMAGE_URL,
            headers={"Authorization": f"Bearer {VENICE_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "chroma",
                "prompt": prompt,
                "width": 512,
                "height": 768 if nude else 512,
                "seed": random.randint(1, 1000000)
            },
            timeout=60
        )
        
        if response.status_code == 200:
            image_data = response.json().get("images", [None])[0]
            if image_data:
                return base64.b64decode(image_data)
        
        return None
        
    except Exception as e:
        logger.error(f"Avatar generation error: {e}")
        return None

def generate_creative_task(user: Dict) -> dict:
    location = user.get('location_type', 'home')
    details = user.get('location_details', '') or 'standard room'
    risk = user.get('risk_level', 3)
    creativity = user.get('creativity_level', 3)
    gender = user.get('avatar_gender', 'female')
    name = user.get('avatar_name', 'Mistress')
    
    recent_hashes = get_recent_hashes(user['chat_id'])
    
    if risk >= 4:
        preferred_cats = ['public_risk', 'exposure', 'degradation', 'edging']
    elif risk >= 3:
        preferred_cats = ['exposure', 'edging', 'degradation', 'position']
    else:
        preferred_cats = ['position', 'service', 'physical', 'exposure']
    
    if random.random() < (creativity / 5):
        selected_category = random.choice(preferred_cats)
    else:
        selected_category = random.choice(list(TASK_CATEGORIES.keys()))
    
    recent_tasks = []
    try:
        session = Session()
        recent = session.query(TaskHistory).filter_by(chat_id=user['chat_id'])\
            .order_by(desc(TaskHistory.assigned_at)).limit(5).all()
        recent_tasks = [t.task_description for t in recent]
        session.close()
    except:
        pass
    
    recent_text = "\n".join([f"- {d[:80]}..." for d in recent_tasks]) if recent_tasks else "None."
    
    social_enabled = user.get('social_media', False)
    social_instruction = "Social media tasks ALLOWED" if social_enabled else "NO social media"
    
    risk_desc = {
        1: "Safe and private",
        2: "Low risk, unlikely to be seen",
        3: "Medium risk, semi-public possible",
        4: "High risk, public exposure likely",
        5: "EXTREME risk - dangerous but ethical, NO unwilling participants"
    }.get(risk, "Medium")
    
    prompt = f"""Create UNIQUE BDSM task (MAX 400 CHARS).

RULES:
- Photo MUST be SELFIE (one hand holding phone)
- Be SPECIFIC - use exact furniture, rooms from location
- NEVER repeat recent tasks:
{recent_text}

CATEGORY: {selected_category.upper()}
RISK {risk}/5: {risk_desc}
{social_instruction}

LOCATION: {location}
DETAILS: {details}

BE SPECIFIC:
- Exact furniture (bed, couch, desk, chair)
- Specific rooms (kitchen, bathroom, bedroom)
- Exact time limits ("8 min", "12 min")
- Exact dress state ("completely naked", "underwear only")

Create CREATIVE task:

TASK:"""

    ai_description = generate_ai_response(prompt, 400, 0.9)
    
    if ai_description:
        ai_description = ai_description.strip().strip('"\'')
        if ai_description.lower().startswith('task:'):
            ai_description = ai_description[5:].strip()
        
        if len(ai_description) > 400:
            ai_description = ai_description[:397] + "..."
        
        if 'selfie' not in ai_description.lower() and 'photo' not in ai_description.lower():
            ai_description += " Selfie proof required."
        
        task_hash = get_task_hash(ai_description)
        if task_hash in recent_hashes:
            return generate_fallback_task(user, selected_category)
        
        return {
            "description": ai_description,
            "task_hash": task_hash,
            "category": selected_category,
            "ai_generated": True,
            "risk_level": risk,
            "location": location
        }
    
    return generate_fallback_task(user, selected_category)

def generate_fallback_task(user: Dict, category: str = None) -> dict:
    location = user.get('location_type', 'home')
    risk = user.get('risk_level', 3)
    name = user.get('avatar_name', 'Mistress')
    
    fallbacks = {
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
            5: [f"Find a secluded outdoor spot, strip completely, photograph yourself"]
        },
        'work': {
            1: [f"Kneel under your desk and photograph"],
            2: [f"Take a risky photo in bathroom stall at work"],
            3: [f"Expose yourself in your office/cubicle when alone"],
            4: [f"Nude photo in work bathroom with company logo visible"],
            5: [f"Step outside work building nude at night for 5 seconds"]
        }
    }
    
    loc_tasks = fallbacks.get(location, fallbacks['home'])
    risk_tasks = loc_tasks.get(risk, loc_tasks[3])
    
    if user.get('social_media', False) and risk >= 4:
        risk_tasks = risk_tasks + [
            "Post exposed photo to Instagram story, screenshot proof",
            "Send risky photo to random contact, screenshot reaction"
        ]
    
    description = random.choice(risk_tasks)
    
    return {
        "description": description,
        "task_hash": get_task_hash(description),
        "category": category or 'general',
        "ai_generated": False,
        "risk_level": risk,
        "location": location
    }

# ==================== SCHEDULER ====================

async def random_interval_check(context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        users = session.query(BotParameters).filter_by(scheduling_enabled=True).all()
        now = datetime.utcnow()
        
        for u in users:
            # Skip if has pending task
            if u.current_task and not u.task_completed:
                continue
            
            # Initialize next_task_time if not set
            if not u.next_task_time:
                min_mins = u.min_interval_minutes or 30
                max_mins = u.max_interval_minutes or 120
                random_minutes = random.randint(min_mins, max_mins)
                u.next_task_time = now + timedelta(minutes=random_minutes)
                session.commit()
                continue
            
            # Check if it's time
            if now < u.next_task_time:
                continue
            
            # SEND TASK
            try:
                user_dict = {c.name: getattr(u, c.name) for c in u.__table__.columns}
                task_data = generate_creative_task(user_dict)
                
                u.current_task = task_data['description']
                u.task_assigned_at = now
                u.task_completed = False
                
                # Set next time
                min_mins = u.min_interval_minutes or 30
                max_mins = u.max_interval_minutes or 120
                random_minutes = random.randint(min_mins, max_mins)
                u.next_task_time = now + timedelta(minutes=random_minutes)
                
                # Update hashes
                recent = u.recent_task_hashes or ''
                hashes = recent.split(',')[-9:] if recent else []
                hashes.append(task_data['task_hash'])
                u.recent_task_hashes = ','.join(hashes)
                
                session.commit()
                
                # Build message
                name = u.avatar_name or 'Mistress'
                risk_emoji = "🔥" * u.risk_level
                ai_badge = "🤖 " if task_data['ai_generated'] else ""
                
                keyboard = [[
                    InlineKeyboardButton("Complete", callback_data="complete_task"),
                    InlineKeyboardButton("Give Up", callback_data="give_up")
                ]]
                
                message_text = f"""{risk_emoji} {ai_badge}*Task from {name}*

{task_data['description']}

⏰ Complete within 30 minutes.

Next task in approximately {random_minutes} minutes."""
                
                # Check if we should send avatar image (sporadic)
                avatar_chance = u.avatar_frequency or 0.3
                send_avatar = random.random() < avatar_chance
                
                if send_avatar:
                    # Generate dominating (non-nude) avatar
                    mood = random.choice(list(AVATAR_MOODS.keys()))
                    image_bytes = generate_avatar_image(user_dict, mood, nude=False)
                    
                    if image_bytes:
                        await context.bot.send_photo(
                            chat_id=u.chat_id,
                            photo=InputFile(io.BytesIO(image_bytes), filename="dom.jpg"),
                            caption=message_text,
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=u.chat_id,
                            text=message_text,
                            parse_mode='Markdown',
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                else:
                    await context.bot.send_message(
                        chat_id=u.chat_id,
                        text=message_text,
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                
                # Log and schedule expire
                log_task(
                    u.chat_id,
                    task_data['description'],
                    task_data['task_hash'],
                    task_data['risk_level'],
                    task_data['location'],
                    'assigned'
                )
                
                asyncio.create_task(auto_expire_task(u.chat_id, 30, context))
                
            except Exception as e:
                logger.error(f"Failed to send task: {e}")
                
    finally:
        session.close()

async def auto_expire_task(chat_id: str, minutes: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(minutes * 60)
    
    user = get_user(chat_id)
    if user.get('current_task') and not user.get('task_completed'):
        name = user.get('avatar_name', 'Mistress')
        
        log_task(
            chat_id,
            user['current_task'],
            get_task_hash(user['current_task']),
            user.get('risk_level', 3),
            user.get('location_type', 'home'),
            'expired'
        )
        
        update_user(chat_id, {
            'total_tasks_failed': user['total_tasks_failed'] + 1,
            'current_streak': 0,
            'points': max(0, user['points'] - 10),
            'current_task': None,
            'task_completed': False
        })
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ *Task Expired*\n\n{name} is disappointed. -10 points.",
            parse_mode='Markdown'
        )

# ==================== HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id, update.effective_user.username)
    
    await update.message.reply_text(
        f"""Welcome to DOM Bot v10.3

Your Chat ID: `{chat_id}`

🎭 */avatar* - Create your dominant
📍 */location* - Set location + details
⏱️ */interval* - Random task interval
🔥 */risk* - Risk level 1-5
🎨 */creativity* - Creativity level
🖼️ */avatarfreq* - Avatar image frequency (0-1)
🚫 */limits* - Kink toggles
📋 */task* - Get task NOW
📊 */status* - Your stats
🎁 */reward* - Nude rewards

✅ Photo verification uses AI vision
✅ Tasks are AI-generated with variety
✅ Sporadic dominating avatar images
✅ Random intervals work correctly"""
    )

async def avatarfreq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /avatarfreq 0.3\n"
            "0 = never send avatar images\n"
            "0.3 = 30% chance (default)\n"
            "0.7 = 70% chance\n"
            "1.0 = always send avatar with task"
        )
        return
    
    try:
        freq = float(context.args[0])
        freq = max(0.0, min(1.0, freq))
        update_user(chat_id, {'avatar_frequency': freq})
        await update.message.reply_text(f"✅ Avatar frequency: {freq:.0%}")
    except ValueError:
        await update.message.reply_text("Use a number between 0 and 1")

async def location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    keyboard = [
        [InlineKeyboardButton(f"🏠 Home", callback_data="loc_home")],
        [InlineKeyboardButton(f"🏢 Work", callback_data="loc_work")],
        [InlineKeyboardButton(f"🌍 Public", callback_data="loc_public")],
        [InlineKeyboardButton("Set Details", callback_data="loc_details")]
    ]
    
    await update.message.reply_text(
        f"📍 Location: {user.get('location_type', 'home').title()}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def loc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    
    if query.data == "loc_details":
        await query.edit_message_text("Use /setdetails <description>")
        return
    
    loc = query.data.replace("loc_", "")
    update_user(chat_id, {'location_type': loc})
    await query.edit_message_text(f"✅ Location: {loc.title()}\nUse /setdetails for specifics.")

async def setdetails(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("Usage: /setdetails 2br apt, roommate home evenings")
        return
    
    details = ' '.join(context.args)
    update_user(chat_id, {'location_details': details})
    await update.message.reply_text(f"✅ Details saved:\n{details}")

async def interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("15-30 min", callback_data="int_15_30"),
         InlineKeyboardButton("30-60 min", callback_data="int_30_60")],
        [InlineKeyboardButton("1-2 hours", callback_data="int_60_120"),
         InlineKeyboardButton("2-4 hours", callback_data="int_120_240")],
        [InlineKeyboardButton("Custom", callback_data="int_custom")]
    ]
    await update.message.reply_text("⏱️ Set interval:", reply_markup=InlineKeyboardMarkup(keyboard))

async def interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    if query.data == "int_custom":
        await query.edit_message_text("Use: /setinterval 45 90")
        return
    
    data = query.data.replace("int_", "")
    min_mins, max_mins = map(int, data.split("_"))
    
    update_user(chat_id, {
        'min_interval_minutes': min_mins,
        'max_interval_minutes': max_mins,
        'scheduling_enabled': True
    })
    await query.edit_message_text(f"✅ {min_mins}-{max_mins} min")

async def setinterval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setinterval <min> <max>")
        return
    
    try:
        min_mins, max_mins = map(int, context.args)
        if min_mins >= max_mins:
            await update.message.reply_text("Min < max!")
            return
        
        update_user(chat_id, {
            'min_interval_minutes': min_mins,
            'max_interval_minutes': max_mins,
            'scheduling_enabled': True
        })
        await update.message.reply_text(f"✅ {min_mins}-{max_mins} min")
    except ValueError:
        await update.message.reply_text("Use numbers")

async def avatar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("👨 Male", callback_data="av_gender_male"),
         InlineKeyboardButton("👩 Female", callback_data="av_gender_female")],
        [InlineKeyboardButton("⚧ Trans", callback_data="av_gender_trans")],
        [InlineKeyboardButton("Customize", callback_data="av_custom")]
    ]
    await update.message.reply_text("Select gender:", reply_markup=InlineKeyboardMarkup(keyboard))

async def av_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    gender = query.data.replace("av_gender_", "")
    name = "Master" if gender == "male" else "Mistress" if gender == "female" else "Domme"
    update_user(chat_id, {'avatar_gender': gender, 'avatar_name': name})
    await query.edit_message_text(f"✅ {gender.title()}. Use /avatar to customize.")

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

async def cycle_avatar_opt(update: Update, context: ContextTypes.DEFAULT_TYPE, option: str, options: list):
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
    await cycle_avatar_opt(update, context, 'ethnicity', ETHNICITIES)

async def av_body_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_avatar_opt(update, context, 'body', BODY_TYPES)

async def av_hair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_avatar_opt(update, context, 'hair_color', HAIR_COLORS)

async def av_pubic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cycle_avatar_opt(update, context, 'pubic', PUBIC_STYLES)

async def av_feature_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    gender = user.get('avatar_gender', 'female')
    
    sizes = FEMALE_SIZES if gender in ['female', 'trans'] else MALE_SIZES
    await cycle_avatar_opt(update, context, 'feature_size', sizes)

async def av_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moods = ['strict', 'playful', 'cruel', 'seductive', 'sadistic']
    await cycle_avatar_opt(update, context, 'mood', moods)

async def av_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Saved!")

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for level, desc in RISK_LEVELS.items():
        keyboard.append([InlineKeyboardButton(f"{level}: {desc[:30]}...", callback_data=f"risk_{level}")])
    await update.message.reply_text("🔥 Set risk:", reply_markup=InlineKeyboardMarkup(keyboard))

async def risk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    level = int(query.data.replace("risk_", ""))
    update_user(chat_id, {'risk_level': level})
    await query.edit_message_text(f"✅ Risk: {level}/5")

async def creativity_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(str(i), callback_data=f"creativity_{i}")] for i in range(1, 6)]
    await update.message.reply_text("🎨 Creativity:", reply_markup=InlineKeyboardMarkup(keyboard))

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
    
    await update.message.reply_text("Limits (click to toggle):", reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data
    
    if data == "limits_done":
        await query.edit_message_text("✅ Updated!")
        return
    
    kink_id = data.replace("toggle_", "")
    toggle_kink(chat_id, kink_id)
    await limits(update, context)

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    
    if user.get('current_task') and not user.get('task_completed'):
        await update.message.reply_text(f"You have a pending task:\n\n{user['current_task']}\n\nComplete it first!")
        return
    
    task_data = generate_creative_task(user)
    risk = user.get('risk_level', 3)
    
    update_user(chat_id, {
        'current_task': task_data['description'],
        'task_assigned_at': datetime.utcnow(),
        'task_completed': False,
        'photo_retry_count': 0
    })
    
    recent = user.get('recent_task_hashes', '')
    hashes = recent.split(',')[-9:] if recent else []
    hashes.append(task_data['task_hash'])
    update_user(chat_id, {'recent_task_hashes': ','.join(hashes)})
    
    log_task(chat_id, task_data['description'], task_data['task_hash'],
             task_data['risk_level'], task_data['location'], 'assigned')
    
    keyboard = [[InlineKeyboardButton("Complete", callback_data="complete_task"),
                 InlineKeyboardButton("Give Up", callback_data="give_up")]]
    
    name = user.get('avatar_name', 'Mistress')
    risk_emoji = "🔥" * risk
    ai_badge = "🤖 " if task_data['ai_generated'] else ""
    
    # Check if we should send avatar image
    avatar_chance = user.get('avatar_frequency', 0.3)
    send_avatar = random.random() < avatar_chance
    
    if send_avatar:
        mood = random.choice(list(AVATAR_MOODS.keys()))
        image_bytes = generate_avatar_image(user, mood, nude=False)
        
        if image_bytes:
            await update.message.reply_photo(
                photo=InputFile(io.BytesIO(image_bytes), filename="dom.jpg"),
                caption=f"""{risk_emoji} {ai_badge}*Task from {name}*

{task_data['description']}

⏰ 30 minutes to complete.""",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"""{risk_emoji} {ai_badge}*Task from {name}*

{task_data['description']}

⏰ 30 minutes to complete.""",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text(
            f"""{risk_emoji} {ai_badge}*Task from {name}*

{task_data['description']}

⏰ 30 minutes to complete.""",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    asyncio.create_task(auto_expire_task(chat_id, 30, context))

async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("📸 Send selfie proof of task completion.")

async def give_up_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    if user.get('current_task'):
        log_task(chat_id, user['current_task'], get_task_hash(user['current_task']),
                 user.get('risk_level', 3), user.get('location_type', 'home'), 'failed')
    
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
        await update.message.reply_text("No active task. Use /task first.")
        return
    
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    analyzing = await update.message.reply_text(f"{name} is analyzing your submission...")
    
    try:
        photo_bytes = await file.download_as_bytearray()
        result = await verify_photo_with_ai(user['current_task'], photo_bytes)
        
        await analyzing.delete()
        
        if result['verified']:
            new_completed = user['total_tasks_completed'] + 1
            new_streak = user['current_streak'] + 1
            new_points = user['points'] + (user.get('risk_level', 3) * 5)
            new_nude = user.get('tasks_since_nude', 0) + 1
            
            log_task(chat_id, user['current_task'], get_task_hash(user['current_task']),
                     user.get('risk_level', 3), user.get('location_type', 'home'),
                     'completed', file.file_path, f"{result['confidence']} confidence", result['full_analysis'])
            
            update_user(chat_id, {
                'total_tasks_completed': new_completed,
                'current_streak': new_streak,
                'longest_streak': max(user['longest_streak'], new_streak),
                'points': new_points,
                'tasks_since_nude': new_nude,
                'current_task': None,
                'task_completed': False,
                'photo_retry_count': 0
            })
            
            nude_msg = ""
            if user.get('nude_reward_enabled', True) and new_nude >= user.get('nude_frequency', 3):
                nude_msg = f"\n\n🎁 Earned nude from {name}! Use /reward"
                update_user(chat_id, {'tasks_since_nude': 0})
            
            await update.message.reply_text(
                f"""✅ *Verified by {name}*

AI Confidence: {result['confidence'].upper()}
Assessment: {result['reasoning']}

Streak: {new_streak} 🔥 | Points: {new_points}{nude_msg}""",
                parse_mode='Markdown'
            )
        else:
            retry = user.get('photo_retry_count', 0) + 1
            
            if retry >= 2:
                log_task(chat_id, user['current_task'], get_task_hash(user['current_task']),
                         user.get('risk_level', 3), user.get('location_type', 'home'),
                         'failed', file.file_path, f"Rejected: {result['reasoning']}", result['full_analysis'])
                
                update_user(chat_id, {
                    'total_tasks_failed': user['total_tasks_failed'] + 1,
                    'current_streak': 0,
                    'points': max(0, user['points'] - 10),
                    'current_task': None,
                    'photo_retry_count': 0
                })
                
                await update.message.reply_text(
                    f"""❌ *Rejected by {name}*

AI Assessment: {result['reasoning']}

Failed verification twice. Task marked as failed."""
                )
            else:
                update_user(chat_id, {'photo_retry_count': retry})
                
                keyboard = [[InlineKeyboardButton("Try Again", callback_data="retry_photo"),
                             InlineKeyboardButton("Give Up", callback_data="give_up_photo")]]
                
                await update.message.reply_text(
                    f"""❌ *{name} rejects this photo*

AI Assessment: {result['reasoning']}

Tries remaining: {2 - retry}""",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
    except Exception as e:
        logger.error(f"Photo handling error: {e}")
        await analyzing.delete()
        await update.message.reply_text("Error analyzing photo. Please try again.")

async def retry_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("Send a clearer selfie showing task completion.")

async def give_up_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    if user.get('current_task'):
        log_task(chat_id, user['current_task'], get_task_hash(user['current_task']),
                 user.get('risk_level', 3), user.get('location_type', 'home'), 'failed')
    
    update_user(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'current_task': None,
        'photo_retry_count': 0
    })
    
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text(f"{name} is disappointed. Task failed.")

async def reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    if not user.get('nude_reward_enabled', True):
        await update.message.reply_text("Nudes disabled.")
        return
    
    progress = user.get('tasks_since_nude', 0)
    needed = user.get('nude_frequency', 3)
    
    if progress >= needed:
        await update.message.reply_text(f"🎁 Generating nude reward from {name}...")
        
        # Generate nude reward image
        image_bytes = generate_avatar_image(user, 'seductive', nude=True)
        
        if image_bytes:
            caption = f"""🎁 *Nude Reward from {name}*

"{name} says: You've been a good pet. Enjoy this view... then get back to serving me."

Next reward in {needed} tasks."""
            
            await update.message.reply_photo(
                photo=InputFile(io.BytesIO(image_bytes), filename="reward.jpg"),
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            # Fallback text
            await update.message.reply_text(
                f"""🎁 *Nude Reward from {name}*

[Image generation failed]

"{name} says: You've earned this reward, pet. Now serve me again." """
            )
        
        update_user(chat_id, {'tasks_since_nude': 0})
    else:
        await update.message.reply_text(
            f"🎁 Progress: {progress}/{needed} tasks for nude reward\nKeep being obedient! 🔥"
        )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    name = user.get('avatar_name', 'Mistress')
    
    current = ""
    if user.get('current_task'):
        current = f"\n🎯 Active: {user['current_task'][:80]}..."
    
    await update.message.reply_text(
        f"""📊 {name}'s Pet

Completed: {user['total_tasks_completed']}
Failed: {user['total_tasks_failed']}
Streak: {user['current_streak']} 🔥 (Best: {user['longest_streak']})
Points: {user['points']}

📍 Location: {user.get('location_type', 'home').title()}
⏱️ Interval: {user.get('min_interval_minutes', 30)}-{user.get('max_interval_minutes', 120)} min
🔥 Risk: {user.get('risk_level', 3)}/5 | 🎨 Creativity: {user.get('creativity_level', 3)}/5
🖼️ Avatar Freq: {user.get('avatar_frequency', 0.3):.0%}
📱 Social Media: {'ON' if user.get('social_media') else 'OFF'}

🎁 Nude Progress: {user.get('tasks_since_nude', 0)}/{user.get('nude_frequency', 3)}
{current}"""
    )

async def resetowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("YES DELETE ALL", callback_data="confirm_reset"),
                 InlineKeyboardButton("Cancel", callback_data="cancel_reset")]]
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
    
    # Scheduler
    job_queue = app.job_queue
    job_queue.run_repeating(random_interval_check, interval=60, first=10)
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("avatar", avatar))
    app.add_handler(CommandHandler("avatarfreq", avatarfreq))
    app.add_handler(CommandHandler("location", location))
    app.add_handler(CommandHandler("setdetails", setdetails))
    app.add_handler(CommandHandler("interval", interval))
    app.add_handler(CommandHandler("setinterval", setinterval_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("creativity", creativity_cmd))
    app.add_handler(CommandHandler("limits", limits))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("reward", reward_cmd))
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
    
    logger.info("DOM Bot v10.3 - Complete with Rewards & Avatars")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()