import os
import json
import logging
import asyncio
import base64
import hashlib
import random
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Float, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ============ CONFIGURATION ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
VENICE_API_KEY = os.getenv('VENICE_API_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')
VENICE_API_URL = "https://api.venice.ai/api/v1"
VENICE_IMAGE_URL = "https://api.venice.ai/api/v1/image/generate"

# ============ DATABASE SETUP ============
Base = declarative_base()

class UserState(Base):
    __tablename__ = 'user_states'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    gender = Column(String(20), default=None)  # male, female, trans, nonbinary
    current_outfit = Column(String(100), default=None)
    outfit_items = Column(Text, default=None)  # JSON list
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
    min_interval = Column(Integer, default=60)  # minutes
    max_interval = Column(Integer, default=180)
    avatar_url = Column(Text, nullable=True)
    
    # Kink toggles (21 total)
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
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    task_text = Column(Text, nullable=False)
    risk_level = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")  # pending, completed, expired, failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    photo_url = Column(Text, nullable=True)
    verification_attempts = Column(Integer, default=0)

class TaskHistory(Base):
    __tablename__ = 'task_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    task_text = Column(Text, nullable=False)
    risk_level = Column(Integer, nullable=False)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AvatarImage(Base):
    __tablename__ = 'avatar_images'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    image_url = Column(Text, nullable=False)
    gender = Column(String(20))
    body_type = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# Database connection
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# ============ CONSTANTS ============

RISK_LEVELS = {
    1: {
        "name": "Safe",
        "description": "Private tasks, no exposure risk",
        "examples": "At home alone, bedroom/bathroom only, no windows visible to outside",
        "exposure": False,
        "public": False
    },
    2: {
        "name": "Low Risk", 
        "description": "Minimal exposure, very low chance of detection",
        "examples": "Indoor with curtains/blinds, backyard with privacy fence, window at night with lights off",
        "exposure": True,
        "public": False
    },
    3: {
        "name": "Medium Risk",
        "description": "Public exposure but minimal chance of being caught",
        "examples": "Empty parking lot at night, deserted park trail, fitting room with locked door, car in remote area, rooftop/elevator when alone, late night gas station when empty",
        "exposure": True,
        "public": True,
        "safety": "Verify location is empty before starting, have escape route planned"
    },
    4: {
        "name": "High Risk",
        "description": "Public exposure with moderate chance of being seen, but deniable/plausible",
        "examples": "Busy parking lot but in backseat with tinted windows, public restroom stall with door locked, hiking trail with time to hide, beach with towel covering, balcony with quick duck-inside option, changing room with curtain",
        "exposure": True,
        "public": True,
        "safety": "Can cover up quickly, plausible deniability if seen, no direct confrontation"
    },
    5: {
        "name": "Extreme Risk",
        "description": "High probability of being caught, direct exposure to public, no easy escape",
        "examples": "Busy sidewalk, restaurant bathroom with thin walls, office with coworkers nearby, hotel hallway, public park during day, window visible to street during day, car in busy lot without tint, balcony in daylight",
        "exposure": True,
        "public": True,
        "safety": "Accept high chance of detection, consequences likely if caught"
    }
}

KINK_CATEGORIES = {
    "kink_exposure": "📸 Exposure",
    "kink_humiliation": "😳 Humiliation", 
    "kink_degradation": "🗑️ Degradation",
    "kink_bondage": "⛓️ Bondage",
    "kink_pain": "🔥 Pain",
    "kink_service": "🙇 Service",
    "kink_edging": "⏱️ Edging/Denial",
    "kink_watersports": "💧 Watersports",
    "kink_exhibitionism": "🎭 Exhibitionism",
    "kink_roleplay": "🎪 Roleplay",
    "kink_petplay": "🐾 Pet Play",
    "kink_feminization": "💄 Feminization",
    "kink_cbt": "🔩 CBT",
    "kink_breathplay": "😮‍💨 Breath Play",
    "kink_sensory": "🙈 Sensory Deprivation",
    "kink_temperature": "🌡️ Temperature Play",
    "kink_marking": "✏️ Marking/Writing",
    "kink_spanking": "👋 Spanking",
    "kink_nipple": "👀 Nipple Play",
    "kink_anal": "🍑 Anal",
    "kink_gags": "🔇 Gags",
    "kink_social_media": "📱 Social Media Exposure"
}

OUTFIT_OPTIONS = {
    "casual": {
        "emoji": "👕",
        "name": "Casual (T-shirt/Jeans/Shorts)",
        "male_items": ["t-shirt", "jeans/shorts", "boxers/briefs", "socks"],
        "female_items": ["t-shirt/tank", "leggings/jeans/shorts", "panties/bra", "socks"]
    },
    "formal": {
        "emoji": "👔",
        "name": "Formal (Button-up/Dress)",
        "male_items": ["button-up shirt", "dress pants", "tie", "boxers/briefs", "belt"],
        "female_items": ["blouse/button-up", "skirt/dress pants", "bra", "panties/thong"]
    },
    "athletic": {
        "emoji": "🎽",
        "name": "Athletic (Tank/Shorts)",
        "male_items": ["tank/athletic shirt", "athletic shorts", "compression shorts/boxers"],
        "female_items": ["sports bra/tank", "leggings/shorts", "panties"]
    },
    "lounge": {
        "emoji": "🛋️",
        "name": "Lounge (Sweats/Hoodie)",
        "male_items": ["hoodie/sweatshirt", "sweatpants", "boxers/briefs"],
        "female_items": ["hoodie/sweatshirt", "sweatpants/leggings", "bralette/panties"]
    },
    "minimal": {
        "emoji": "🩳",
        "name": "Minimal (Just Underwear)",
        "male_items": ["boxers/briefs only", "optional socks"],
        "female_items": ["bra/panties only", "optional socks"]
    },
    "custom": {
        "emoji": "✏️",
        "name": "Custom (Describe)",
        "male_items": ["user_defined"],
        "female_items": ["user_defined"]
    }
}

GENDER_TASK_GUIDELINES = {
    "male": {
        "body_parts": ["chest", "abs", "cock", "balls", "ass", "thighs", "back", "shoulders"],
        "clothing_items": ["boxers", "briefs", "t-shirt", "button-up shirt", "pants", "shorts", "socks", "shoes", "belt", "tie", "suit jacket"],
        "underwear_types": ["boxers", "briefs", "jockstrap", "compression shorts"],
        "cannot_do": ["cleavage", "bra", "panties", "skirt", "dress", "heels", "stockings"]
    },
    "female": {
        "body_parts": ["cleavage", "breasts", "nipples", "pussy", "ass", "thighs", "stomach", "back"],
        "clothing_items": ["bra", "panties", "thong", "dress", "skirt", "blouse", "shirt", "pants", "shorts", "heels", "flats", "stockings", "socks"],
        "underwear_types": ["panties", "thong", "boyshorts", "bra", "bralette"],
        "cannot_do": ["cock", "balls", "jockstrap", "boxers"]
    },
    "trans": {
        "body_parts": ["chest", "breasts", "cock", "clit", "pussy", "ass", "thighs", "stomach"],
        "clothing_items": ["bra", "panties", "thong", "dress", "skirt", "blouse", "shirt", "boxers", "briefs", "heels", "flats", "stockings"],
        "underwear_types": ["panties", "thong", "bra", "boxers", "briefs"],
        "cannot_do": []
    },
    "nonbinary": {
        "body_parts": ["chest", "breasts", "genitals", "ass", "thighs", "stomach"],
        "clothing_items": ["binder", "bra", "underwear", "dress", "skirt", "pants", "shorts", "shirt", "blouse", "heels", "boots", "flats"],
        "underwear_types": ["boxers", "briefs", "panties", "thong", "bra", "binder"],
        "cannot_do": []
    }
}

# ============ HELPER FUNCTIONS ============

def get_user_kinks(user):
    """Get list of enabled kinks for user"""
    enabled = []
    for kink_key, kink_name in KINK_CATEGORIES.items():
        if getattr(user, kink_key, False):
            enabled.append(kink_key.replace("kink_", ""))
    return enabled

async def generate_ai_response(prompt, temperature=0.8):
    """Generate response from Venice AI"""
    try:
        headers = {
            "Authorization": f"Bearer {VENICE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "claude-opus-4-8-fast",
            "messages": [
                {"role": "system", "content": "You are a dominant AI creating BDSM tasks. Be creative, specific, and demanding. Never include time durations like 'for 5 minutes' - tasks are single actions proven by photo only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 500
        }
        
        response = requests.post(
            f"{VENICE_API_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            logger.error(f"AI API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating AI response: {e}")
        return None

async def analyze_image_with_ai(image_bytes, task_description):
    """Analyze photo with Venice AI vision"""
    try:
        headers = {
            "Authorization": f"Bearer {VENICE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Encode image to base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        data = {
            "model": "claude-opus-4-8-fast",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Task: {task_description}\n\nDoes this photo show the task completed? Reply VERIFIED: yes/no and REASON: explanation"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 200
        }
        
        response = requests.post(
            f"{VENICE_API_URL}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            logger.error(f"Vision API error: {response.status_code}")
            return "VERIFIED: no\nREASON: Could not analyze image"
            
    except Exception as e:
        logger.error(f"Error analyzing image: {e}")
        return "VERIFIED: no\nREASON: Error processing image"

def parse_verification(response):
    """Parse AI verification response"""
    verified = "no"
    reason = "Unknown"
    
    if "VERIFIED: yes" in response or "verified: yes" in response.lower():
        verified = "yes"
    
    # Extract reason
    if "REASON:" in response:
        reason = response.split("REASON:")[1].strip()
    elif "reason:" in response.lower():
        reason = response.lower().split("reason:")[1].strip()
    
    return verified, reason

# ============ COMMAND HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "sub"
    
    session = get_session()
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            user = UserState(user_id=user_id, username=username)
            session.add(user)
            session.commit()
            
            # New user - ask for gender first
            keyboard = [
                [InlineKeyboardButton("👨 Male", callback_data="gender_male")],
                [InlineKeyboardButton("👩 Female", callback_data="gender_female")],
                [InlineKeyboardButton("⚧ Trans", callback_data="gender_trans")],
                [InlineKeyboardButton("🌈 Non-binary", callback_data="gender_nonbinary")]
            ]
            
            await update.message.reply_text(
                f"Welcome, {username}. I'm your DOM Bot.\n\n"
                f"To personalize your experience, please select your gender:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        else:
            gender_msg = f"Gender: {user.gender.capitalize()}" if user.gender else "Gender: Not set (/gender to set)"
            outfit_msg = f"Outfit: {user.current_outfit}" if user.current_outfit else "Outfit: Not set (/outfit to set)"
            
            await update.message.reply_text(
                f"Welcome back, {username}.\n\n"
                f"{gender_msg}\n"
                f"{outfit_msg}\n"
                f"Risk Level: {user.risk_level}\n\n"
                f"Commands:\n"
                f"/task - Get a challenge\n"
                f"/outfit - Set your clothing\n"
                f"/gender - Change gender\n"
                f"/risk - Set risk level (1-5)\n"
                f"/kinks - Toggle kinks\n"
                f"/status - Check current task\n"
                f"/schedule - Auto-task settings\n"
                f"/reward - View your avatar rewards"
            )
    finally:
        session.close()

async def gender_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set or change gender"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("👨 Male", callback_data="gender_male")],
        [InlineKeyboardButton("👩 Female", callback_data="gender_female")],
        [InlineKeyboardButton("⚧ Trans", callback_data="gender_trans")],
        [InlineKeyboardButton("🌈 Non-binary", callback_data="gender_nonbinary")]
    ]
    
    await update.message.reply_text(
        "Select your gender for personalized tasks:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gender selection"""
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
            
            gender_emoji = {"male": "👨", "female": "👩", "trans": "⚧", "nonbinary": "🌈"}.get(gender, "❓")
            
            await query.edit_message_text(
                f"{gender_emoji} Gender set to: {gender.capitalize()}\n\n"
                f"Use /outfit to set what you're wearing."
            )
    finally:
        session.close()

async def outfit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set current outfit"""
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user or not user.gender:
            await update.message.reply_text("Please set your gender first with /gender")
            return
        
        keyboard = []
        for key, outfit in OUTFIT_OPTIONS.items():
            keyboard.append([InlineKeyboardButton(
                f"{outfit['emoji']} {outfit['name']}", 
                callback_data=f"outfit_{key}"
            )])
        
        current = user.current_outfit or "Not set"
        await update.message.reply_text(
            f"Current outfit: {current}\n\nWhat are you wearing right now?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def outfit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle outfit selection"""
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
            await query.edit_message_text(
                "Describe what you're wearing:\n"
                "Example: 'White tank top, grey sweatpants, black boxers'\n\n"
                "Send your outfit description now."
            )
            return
        
        outfit = OUTFIT_OPTIONS[outfit_key]
        gender_items = outfit.get(f"{user.gender}_items", outfit["male_items"])
        
        user.current_outfit = outfit["name"]
        user.outfit_items = json.dumps(gender_items)
        session.commit()
        
        items_text = "\n".join([f"  • {item}" for item in gender_items])
        
        await query.edit_message_text(
            f"{outfit['emoji']} Outfit set: {outfit['name']}\n\n"
            f"Items detected:\n{items_text}\n\n"
            f"Ready for tasks! Use /task to begin."
        )
    finally:
        session.close()

async def handle_custom_outfit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom outfit description"""
    if not context.user_data.get('awaiting_custom_outfit'):
        return
    
    user_id = update.effective_user.id
    custom_outfit = update.message.text
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.current_outfit = f"Custom: {custom_outfit[:50]}"
            items = [item.strip() for item in custom_outfit.split(',')]
            user.outfit_items = json.dumps(items[:6])
            session.commit()
            
            await update.message.reply_text(
                f"✅ Custom outfit recorded.\n\nReady for tasks! Use /task to begin."
            )
    finally:
        session.close()
    
    context.user_data['awaiting_custom_outfit'] = False

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set risk level"""
    keyboard = [
        [InlineKeyboardButton("1️⃣ Safe (Private only)", callback_data="risk_1")],
        [InlineKeyboardButton("2️⃣ Low Risk (Minimal exposure)", callback_data="risk_2")],
        [InlineKeyboardButton("3️⃣ Medium Risk (Empty public)", callback_data="risk_3")],
        [InlineKeyboardButton("4️⃣ High Risk (Public with cover)", callback_data="risk_4")],
        [InlineKeyboardButton("5️⃣ Extreme Risk (Likely caught)", callback_data="risk_5")]
    ]
    
    await update.message.reply_text(
        "Select your risk level:\n\n"
        "1️⃣ Safe - Home only, no exposure\n"
        "2️⃣ Low - Minimal exposure, very safe\n"
        "3️⃣ Medium - Public but empty locations\n"
        "4️⃣ High - Public with quick escape\n"
        "5️⃣ Extreme - High chance of being caught",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def risk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle risk selection"""
    query = update.callback_query
    await query.answer()
    
    risk_level = int(query.data.replace("risk_", ""))
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.risk_level = risk_level
            session.commit()
            
            risk_info = RISK_LEVELS[risk_level]
            await query.edit_message_text(
                f"Risk level set to {risk_level}: {risk_info['name']}\n\n"
                f"{risk_info['description']}\n\n"
                f"Examples: {risk_info['examples']}"
            )
    finally:
        session.close()

async def kinks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show kink toggle menu"""
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        keyboard = []
        for kink_key, kink_name in KINK_CATEGORIES.items():
            enabled = getattr(user, kink_key, False)
            status = "✅" if enabled else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{status} {kink_name}", 
                callback_data=f"toggle_{kink_key}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Done", callback_data="kinks_done")])
        
        await update.message.reply_text(
            "Toggle your kinks (click to enable/disable):\n\n"
            "✅ = Enabled\n"
            "❌ = Disabled",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    finally:
        session.close()

async def toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle kink toggle"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "kinks_done":
        await query.edit_message_text("Kinks updated! Use /task to get challenges.")
        return
    
    kink_key = query.data.replace("toggle_", "")
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user and hasattr(user, kink_key):
            current = getattr(user, kink_key, False)
            setattr(user, kink_key, not current)
            session.commit()
            
            # Rebuild keyboard
            keyboard = []
            for key, name in KINK_CATEGORIES.items():
                enabled = getattr(user, key, False)
                status = "✅" if enabled else "❌"
                keyboard.append([InlineKeyboardButton(
                    f"{status} {name}", 
                    callback_data=f"toggle_{key}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 Done", callback_data="kinks_done")])
            
            await query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))
    finally:
        session.close()

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a task"""
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        if not user.gender:
            await update.message.reply_text("Set your gender first with /gender")
            return
        
        if not user.current_outfit:
            await outfit_cmd(update, context)
            return
        
        # Check for existing active task
        active_task = session.query(Task).filter_by(
            user_id=user_id, 
            status="pending"
        ).first()
        
        if active_task:
            time_left = active_task.expires_at - datetime.now(timezone.utc)
            minutes_left = max(0, time_left.total_seconds() / 60)
            
            await update.message.reply_text(
                f"You already have an active task!\n\n"
                f"{active_task.task_text[:200]}...\n\n"
                f"Time remaining: {minutes_left:.0f} minutes\n"
                f"Send photo proof or use /status to check."
            )
            return
        
        # Generate new task
        await update.message.reply_text("Generating your task...")
        
        task_text = await generate_outfit_task(user)
        
        if not task_text:
            await update.message.reply_text("Error generating task. Try again.")
            return
        
        # Create task with 30-minute timeout
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=30)
        
        task = Task(
            user_id=user_id,
            task_text=task_text,
            risk_level=user.risk_level,
            created_at=now,
            expires_at=expires,
            status="pending"
        )
        session.add(task)
        session.commit()
        
        # Schedule timeout
        schedule_task_timeout(user_id, task.id, 30)
        
        # Send task
        keyboard = [
            [InlineKeyboardButton("📸 Send Photo", callback_data=f"complete_{task.id}")],
            [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
        ]
        
        await update.message.reply_text(
            f"🎯 TASK (Risk Level {user.risk_level})\n\n"
            f"Outfit: {user.current_outfit}\n\n"
            f"{task_text}\n\n"
            f"Complete the action and send a photo as proof.\n"
            f"You have 30 minutes.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    finally:
        session.close()

async def generate_outfit_task(user):
    """Generate task based on outfit and gender"""
    
    outfit_items = json.loads(user.outfit_items or '[]')
    gender = user.gender or "nonbinary"
    risk_level = user.risk_level or 1
    kinks = get_user_kinks(user)
    
    items_text = ", ".join(outfit_items) if outfit_items else "clothing"
    gender_guide = GENDER_TASK_GUIDELINES.get(gender, GENDER_TASK_GUIDELINES["nonbinary"])
    body_parts = ", ".join(gender_guide["body_parts"])
    cannot_do = ", ".join(gender_guide["cannot_do"]) if gender_guide["cannot_do"] else "none"
    
    risk_info = RISK_LEVELS.get(risk_level, RISK_LEVELS[1])
    
    kink_text = ""
    if kinks:
        kink_text = f"\nEnabled kinks to incorporate: {', '.join(kinks)}"
    
    prompt = f"""Generate a BDSM exposure task for a {gender} submissive at risk level {risk_level}.

CURRENT OUTFIT: {user.current_outfit}
AVAILABLE CLOTHING ITEMS: {items_text}
AVAILABLE BODY PARTS: {body_parts}
CANNOT INCLUDE: {cannot_do}
RISK DESCRIPTION: {risk_info['description']}{kink_text}

CRITICAL RULES:
- NO time durations (never "for 5 minutes", "hold for 10 minutes")
- Tasks are SINGLE ACTIONS completed by taking ONE photo
- ONLY use clothing items listed above
- ONLY reference body parts this gender has
- NEVER reference: {cannot_do}
- Simple, immediate exposure actions only
- Photo proves completion

EXAMPLES BY RISK:
Level 1: "Strip completely nude in your bedroom and photograph"
Level 2: "Stand nude in front of window at night with lights off, take photo"
Level 3: "Strip nude in backseat of car in empty parking lot, selfie from above"
Level 4: "Expose yourself in backseat of busy parking lot, stay low, photograph"
Level 5: "Stand nude in front of window visible to street during day, photograph"

Generate a specific task using ONLY: {items_text}"""

    response = await generate_ai_response(prompt)
    
    if response:
        # Post-filter for marking kink
        if "kink_marking" not in kinks:
            marking_words = ["write", "marker", "sharpie", "draw on", "body writing", "marking"]
            if any(word in response.lower() for word in marking_words):
                # Fallback to safe task
                return f"Strip completely and take a photo showing your {random.choice(gender_guide['body_parts'][:3])}"
        
        return response.strip()
    
    # Fallback
    return f"Strip completely nude and take a photo proving completion."

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check task status with debug info"""
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if not user:
            await update.message.reply_text("Use /start first")
            return
        
        active_task = session.query(Task).filter_by(
            user_id=user_id,
            status="pending"
        ).first()
        
        now = datetime.now(timezone.utc)
        
        if active_task:
            time_left = active_task.expires_at - now
            minutes_left = max(0, time_left.total_seconds() / 60)
            
            debug_info = (
                f"🎯 ACTIVE TASK\n\n"
                f"{active_task.task_text[:200]}...\n\n"
                f"⏰ Time remaining: {minutes_left:.0f} minutes\n"
                f"Risk Level: {active_task.risk_level}\n\n"
                f"Send photo to complete or use buttons below."
            )
            
            keyboard = [
                [InlineKeyboardButton("📸 Complete", callback_data=f"complete_{active_task.id}")],
                [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{active_task.id}")]
            ]
            
            await update.message.reply_text(
                debug_info,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "No active task.\n\n"
                f"Points: {user.points}\n"
                f"Streak: {user.streak}\n"
                f"Risk Level: {user.risk_level}\n\n"
                f"Use /task to get a challenge!"
            )
        
    finally:
        session.close()

# ============ PHOTO HANDLING ============

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo upload for task completion"""
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        # Find active task
        task = session.query(Task).filter_by(
            user_id=user_id,
            status="pending"
        ).first()
        
        if not task:
            await update.message.reply_text(
                "No active task to complete. Use /task to get one."
            )
            return
        
        # Check if expired
        now = datetime.now(timezone.utc)
        if now > task.expires_at:
            await update.message.reply_text(
                "⏰ This task has expired. Use /task for a new one."
            )
            task.status = "expired"
            session.commit()
            return
        
        # Download photo
        photo = update.message.photo[-1]  # Highest resolution
        file = await context.bot.get_file(photo.file_id)
        
        await update.message.reply_text("📸 Analyzing your photo...")
        
        # Download bytes
        photo_bytes = await file.download_as_bytearray()
        
        if len(photo_bytes) < 1000:
            await update.message.reply_text(
                "Photo too small or corrupted. Please send a clearer photo."
            )
            return
        
        # Verify with AI
        verification = await analyze_image_with_ai(photo_bytes, task.task_text)
        verified, reason = parse_verification(verification)
        
        task.verification_attempts += 1
        
        if verified == "yes":
            # Task complete!
            task.status = "completed"
            task.completed_at = now
            task.photo_url = f"photo_{task.id}"  # Store reference
            
            # Update user stats
            user = session.query(UserState).filter_by(user_id=user_id).first()
            user.points += 10 * task.risk_level
            user.streak += 1
            user.completed_tasks += 1
            user.consecutive_failures = 0
            
            # Check for avatar reward (every 5 tasks)
            reward_msg = ""
            if user.completed_tasks % 5 == 0:
                reward_msg = "\n\n🎁 REWARD UNLOCKED! Use /reward to generate your avatar."
            
            session.commit()
            
            await update.message.reply_text(
                f"✅ TASK COMPLETED!\n\n"
                f"+{10 * task.risk_level} points\n"
                f"Streak: {user.streak}\n"
                f"Total points: {user.points}{reward_msg}"
            )
            
        else:
            # Failed verification
            if task.verification_attempts >= 2:
                # Max retries reached
                task.status = "failed"
                user = session.query(UserState).filter_by(user_id=user_id).first()
                user.consecutive_failures += 1
                session.commit()
                
                await update.message.reply_text(
                    f"❌ VERIFICATION FAILED\n\n"
                    f"Reason: {reason}\n\n"
                    f"You've used all retries. Task marked as failed.\n"
                    f"Use /task for a new challenge."
                )
            else:
                # Offer retry
                keyboard = [
                    [InlineKeyboardButton("🔄 Try Again", callback_data=f"retry_{task.id}")],
                    [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
                ]
                
                await update.message.reply_text(
                    f"❌ Photo rejected\n\n"
                    f"Reason: {reason}\n\n"
                    f"You have {2 - task.verification_attempts} retry left.\n"
                    f"Try again or give up?",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        
        session.commit()
        
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await update.message.reply_text(
            "Error processing photo. Please try again."
        )
    finally:
        session.close()

async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to send photo"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.replace("complete_", ""))
    
    await query.edit_message_text(
        "📸 Send your photo proof now.\n\n"
        "Make sure the photo clearly shows the task completed."
    )

async def giveup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle give up"""
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
            user.consecutive_failures += 1
            
            session.commit()
            
            await query.edit_message_text(
                "❌ Task abandoned.\n\n"
                "-5 points. Streak reset.\n"
                "Use /task for a new challenge."
            )
    finally:
        session.close()

async def retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle retry request"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📸 Send your retry photo now.\n\n"
        "Make sure it clearly shows the task requirements."
    )

# ============ SCHEDULER ============

scheduler = AsyncIOScheduler()

def schedule_task_timeout(user_id, task_id, minutes):
    """Schedule task timeout"""
    run_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    
    scheduler.add_job(
        auto_clear_task,
        'date',
        run_date=run_time,
        args=[user_id, task_id],
        id=f"timeout_{task_id}",
        replace_existing=True
    )

async def auto_clear_task(user_id, task_id):
    """Auto-clear expired task"""
    logger.info(f"Auto-clear for task {task_id}")
    
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id).first()
        
        if not task or task.status != "pending":
            return
        
        # Mark expired
        task.status = "expired"
        
        user = session.query(UserState).filter_by(user_id=user_id).first()
        if user:
            user.points = max(0, user.points - 10)
            user.streak = 0
            user.consecutive_failures += 1
            session.commit()
            
            # Notify user
            try:
                await Application.builder().token(TELEGRAM_TOKEN).build().bot.send_message(
                    chat_id=user_id,
                    text="⏰ TASK EXPIRED\n\nYou failed to complete in time.\n-10 points. Streak reset.\n\nUse /task for a new challenge."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
        
        session.commit()
        
    except Exception as e:
        logger.error(f"Error in auto_clear_task: {e}")
    finally:
        session.close()

async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure auto-task scheduling"""
    keyboard = [
        [InlineKeyboardButton("▶️ Enable Auto-Tasks", callback_data="sched_enable")],
        [InlineKeyboardButton("⏹️ Disable Auto-Tasks", callback_data="sched_disable")],
        [InlineKeyboardButton("⏱️ Set Interval", callback_data="sched_interval")]
    ]
    
    await update.message.reply_text(
        "Auto-Task Scheduler\n\n"
        "When enabled, I'll send you tasks automatically at random intervals.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle schedule settings"""
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
            await query.edit_message_text("✅ Auto-tasks enabled! You'll receive tasks automatically.")
            
        elif query.data == "sched_disable":
            user.scheduling_enabled = False
            user.next_task_time = None
            session.commit()
            await query.edit_message_text("⏹️ Auto-tasks disabled.")
            
        elif query.data == "sched_interval":
            await query.edit_message_text(
                "Send me the interval range in minutes (e.g., '60 180' for 1-3 hours):"
            )
            context.user_data['awaiting_interval'] = True
            
    finally:
        session.close()

async def handle_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interval input"""
    if not context.user_data.get('awaiting_interval'):
        return
    
    try:
        parts = update.message.text.split()
        min_int = int(parts[0])
        max_int = int(parts[1])
        
        if min_int < 10 or max_int > 1440 or min_int >= max_int:
            await update.message.reply_text("Invalid range. Use format: '60 180' (min max, 10-1440 minutes)")
            return
        
        user_id = update.effective_user.id
        session = get_session()
        
        try:
            user = session.query(UserState).filter_by(user_id=user_id).first()
            user.min_interval = min_int
            user.max_interval = max_int
            session.commit()
            
            await update.message.reply_text(f"✅ Interval set: {min_int}-{max_int} minutes")
        finally:
            session.close()
            
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid format. Use: '60 180'")
    
    context.user_data['awaiting_interval'] = False

async def random_interval_check():
    """Check for users due for auto-tasks"""
    session = get_session()
    try:
        now = datetime.now(timezone.utc)
        
        users = session.query(UserState).filter(
            UserState.scheduling_enabled == True,
            UserState.next_task_time <= now
        ).all()
        
        for user in users:
            # Check no active task
            active = session.query(Task).filter_by(
                user_id=user.user_id,
                status="pending"
            ).first()
            
            if not active:
                # Send task
                try:
                    app = Application.builder().token(TELEGRAM_TOKEN).build()
                    
                    task_text = await generate_outfit_task(user)
                    if task_text:
                        expires = now + timedelta(minutes=30)
                        
                        task = Task(
                            user_id=user.user_id,
                            task_text=task_text,
                            risk_level=user.risk_level,
                            created_at=now,
                            expires_at=expires,
                            status="pending"
                        )
                        session.add(task)
                        
                        schedule_task_timeout(user.user_id, task.id, 30)
                        
                        keyboard = [
                            [InlineKeyboardButton("📸 Send Photo", callback_data=f"complete_{task.id}")],
                            [InlineKeyboardButton("❌ Give Up", callback_data=f"giveup_{task.id}")]
                        ]
                        
                        await app.bot.send_message(
                            chat_id=user.user_id,
                            text=f"🎯 AUTO TASK (Risk {user.risk_level})\n\n{task_text}\n\nYou have 30 minutes.",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        # Schedule next
                        user.next_task_time = now + timedelta(minutes=random.randint(user.min_interval, user.max_interval))
                        session.commit()
                        
                except Exception as e:
                    logger.error(f"Error sending auto-task to {user.user_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Error in interval check: {e}")
    finally:
        session.close()

# ============ AVATAR REWARDS ============

async def reward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate avatar reward"""
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        user = session.query(UserState).filter_by(user_id=user_id).first()
        
        if not user or not user.gender:
            await update.message.reply_text("Set your gender first with /gender")
            return
        
        # Check if earned
        if user.completed_tasks < 5:
            await update.message.reply_text(
                f"Complete {5 - (user.completed_tasks % 5)} more tasks to unlock your next avatar reward!"
            )
            return
        
        await update.message.reply_text("🎨 Generating your avatar reward...")
        
        # Generate avatar
        image_url = await generate_avatar_reward(user)
        
        if image_url:
            # Save to history
            avatar = AvatarImage(
                user_id=user_id,
                image_url=image_url,
                gender=user.gender
            )
            session.add(avatar)
            session.commit()
            
            await update.message.reply_photo(
                photo=image_url,
                caption="🎁 Your reward for completing tasks!\n\nUse /reward to generate another (every 5 tasks)."
            )
        else:
            await update.message.reply_text("Error generating reward. Try again later.")
            
    finally:
        session.close()

async def generate_avatar_reward(user):
    """Generate avatar image using Venice"""
    try:
        gender = user.gender
        gender_descriptors = {
            "male": "male man masculine, muscular or slim build",
            "female": "female woman feminine, curvy or slim build",
            "trans": "trans feminine, breasts and penis, feminine curves",
            "nonbinary": "androgynous nonbinary person"
        }
        
        desc = gender_descriptors.get(gender, "person")
        
        prompt = f"Beautiful {desc}, nude, erotic pose, submissive, high quality, detailed skin, professional photography"
        
        headers = {
            "Authorization": f"Bearer {VENICE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "chroma",
            "prompt": prompt,
            "width": 512,
            "height": 768,
            "seed": random.randint(1, 1000000)
        }
        
        response = requests.post(
            VENICE_IMAGE_URL,
            headers=headers,
            json=data,
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'images' in result and len(result['images']) > 0:
                return result['images'][0]
        
        logger.error(f"Avatar generation failed: {response.status_code}")
        return None
        
    except Exception as e:
        logger.error(f"Error generating avatar: {e}")
        return None

# ============ RESET COMMAND ============

async def resetowner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset all user data for handoff"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("⚠️ YES, DELETE ALL DATA", callback_data="reset_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="reset_cancel")]
    ]
    
    await update.message.reply_text(
        "⚠️ WARNING: RESET OWNER ⚠️\n\n"
        "This will DELETE all your data:\n"
        "- Task history\n"
        "- Points and streak\n"
        "- Kink preferences\n"
        "- Avatar rewards\n"
        "- All settings\n\n"
        "This cannot be undone. Are you sure?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reset confirmation"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "reset_cancel":
        await query.edit_message_text("Reset cancelled. Your data is safe.")
        return
    
    user_id = update.effective_user.id
    session = get_session()
    
    try:
        # Delete all user data
        session.query(Task).filter_by(user_id=user_id).delete()
        session.query(TaskHistory).filter_by(user_id=user_id).delete()
        session.query(AvatarImage).filter_by(user_id=user_id).delete()
        session.query(UserState).filter_by(user_id=user_id).delete()
        session.commit()
        
        await query.edit_message_text(
            "✅ All data deleted.\n\n"
            "The bot is ready for a new owner.\n"
            "Send /start to begin fresh."
        )
        
    except Exception as e:
        logger.error(f"Error resetting user: {e}")
        await query.edit_message_text("Error deleting data. Please try again.")
    finally:
        session.close()

# ============ MAIN ============

def main():
    """Start the bot"""
    # Start scheduler
    scheduler.start()
    
    # Add interval job
    scheduler.add_job(
        random_interval_check,
        IntervalTrigger(minutes=1),
        id="interval_check",
        replace_existing=True
    )
    
    # Build application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("gender", gender_cmd))
    application.add_handler(CommandHandler("outfit", outfit_cmd))
    application.add_handler(CommandHandler("risk", risk_cmd))
    application.add_handler(CommandHandler("kinks", kinks_cmd))
    application.add_handler(CommandHandler("task", task_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("schedule", schedule_cmd))
    application.add_handler(CommandHandler("reward", reward_cmd))
    application.add_handler(CommandHandler("resetowner", resetowner_cmd))
    application.add_handler(CommandHandler("help", start))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    application.add_handler(CallbackQueryHandler(outfit_callback, pattern="^outfit_"))
    application.add_handler(CallbackQueryHandler(risk_callback, pattern="^risk_"))
    application.add_handler(CallbackQueryHandler(toggle_callback, pattern="^toggle_|^kinks_done"))
    application.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_"))
    application.add_handler(CallbackQueryHandler(giveup_callback, pattern="^giveup_"))
    application.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    application.add_handler(CallbackQueryHandler(schedule_callback, pattern="^sched_"))
    application.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_custom_outfit
    ))
    
    # Start bot
    logger.info("Starting DOM Bot v11...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()