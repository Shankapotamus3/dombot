#!/usr/bin/env python3
"""
DOM Bot v7.2 - Strict Kink Filtering
Auto-capture Chat ID, 30-min timeouts, photo retry with explanations
"""

import os
import logging
import asyncio
import random
import json
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
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Enum, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set!")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# Venice AI Configuration
VENVENICE_API_KEY = os.getenv('VENVENICE_API_KEY')
VENVENICE_MODEL = "claude-opus-4-8-fast"

# Kink categories
KINK_CATEGORIES = {
    'exposure': 'Exposure/Exhibitionism',
    'humiliation': 'Humiliation',
    'degradation': 'Degradation',
    'bondage': 'Bondage/Restraint',
    'pain': 'Pain Play',
    'service': 'Service Tasks',
    'edging': 'Edging/Orgasm Control',
    'watersports': 'Watersports',
    'exhibitionism': 'Exhibitionism',
    'roleplay': 'Roleplay',
    'petplay': 'Pet Play',
    'feminization': 'Feminization',
    'CBT': 'CBT',
    'breathplay': 'Breath Play',
    'sensory': 'Sensory Deprivation',
    'temperature': 'Temperature Play',
    'marking': 'Marking/Writing',
    'spanking': 'Spanking',
    'nipple': 'Nipple Play',
    'anal': 'Anal Play',
    'gags': 'Gags/Muffling'
}

# ==================== DATABASE MODELS ====================

class BotParameters(Base):
    __tablename__ = 'bot_parameters'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, unique=True, nullable=False)
    
    # Kink preferences - all default to True
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
    CBT = Column(Boolean, default=True)
    breathplay = Column(Boolean, default=True)
    sensory = Column(Boolean, default=True)
    temperature = Column(Boolean, default=True)
    marking = Column(Boolean, default=True)
    spanking = Column(Boolean, default=True)
    nipple = Column(Boolean, default=True)
    anal = Column(Boolean, default=True)
    gags = Column(Boolean, default=True)
    
    # Current task tracking
    current_task = Column(Text)
    task_assigned_at = Column(DateTime)
    task_completed = Column(Boolean, default=False)
    photo_retry_count = Column(Integer, default=0)
    
    # Stats
    total_tasks_completed = Column(Integer, default=0)
    total_tasks_failed = Column(Integer, default=0)
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    points = Column(Integer, default=0)

class TaskHistory(Base):
    __tablename__ = 'task_history'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, nullable=False)
    task_description = Column(Text, nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String, default='assigned')
    verification_photo_url = Column(String)
    feedback = Column(Text)

class ConversationMessage(Base):
    __tablename__ = 'conversation_messages'
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, nullable=False)
    role = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(engine)

# ==================== DATABASE HELPERS ====================

def get_or_create_user(chat_id: str) -> Dict[str, Any]:
    """Get user as dictionary to avoid DetachedInstanceError"""
    session = Session()
    try:
        user = session.query(BotParameters).filter_by(chat_id=str(chat_id)).first()
        if not user:
            user = BotParameters(chat_id=str(chat_id))
            session.add(user)
            session.commit()
            logger.info(f"Created new user: {chat_id}")
        
        # Convert to dict
        user_dict = {c.name: getattr(user, c.name) for c in user.__table__.columns}
        return user_dict
    finally:
        session.close()

def update_user_fields(chat_id: str, updates: Dict[str, Any]):
    """Update multiple fields"""
    session = Session()
    try:
        user = session.query(BotParameters).filter_by(chat_id=str(chat_id)).first()
        if user:
            for field, value in updates.items():
                setattr(user, field, value)
            session.commit()
            return True
        return False
    finally:
        session.close()

def toggle_kink(chat_id: str, kink_id: str) -> bool:
    """Toggle a kink preference"""
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

def log_task_history(chat_id: str, task: str, status: str, photo_url: str = None, feedback: str = None):
    """Log task to history"""
    session = Session()
    try:
        history = TaskHistory(
            chat_id=str(chat_id),
            task_description=task,
            status=status,
            verification_photo_url=photo_url,
            feedback=feedback
        )
        session.add(history)
        session.commit()
    finally:
        session.close()

def get_task_history(chat_id: str, limit: int = 10) -> List[Dict]:
    """Get task history"""
    session = Session()
    try:
        history = session.query(TaskHistory).filter_by(chat_id=str(chat_id))\
            .order_by(TaskHistory.assigned_at.desc()).limit(limit).all()
        return [{'task': h.task_description, 'status': h.status, 'feedback': h.feedback} for h in history]
    finally:
        session.close()

def delete_all_user_data(chat_id: str):
    """Delete all user data"""
    session = Session()
    try:
        session.query(BotParameters).filter_by(chat_id=str(chat_id)).delete()
        session.query(TaskHistory).filter_by(chat_id=str(chat_id)).delete()
        session.query(ConversationMessage).filter_by(chat_id=str(chat_id)).delete()
        session.commit()
        return True
    finally:
        session.close()

# ==================== AI INTEGRATION ====================

def generate_ai_response(prompt: str, max_tokens: int = 500) -> str:
    """Generate response using Venice AI"""
    if not VENVENICE_API_KEY:
        logger.error("VENVENICE_API_KEY not set!")
        return None
    
    try:
        response = requests.post(
            "https://api.venice.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {VENVENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": VENVENICE_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a dominant AI assistant. Be commanding but respectful of boundaries."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.8
            },
            timeout=30
        )
        
        logger.info(f"Venice API status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            logger.error(f"Venice API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error calling Venice AI: {e}")
        return None

def generate_task(intensity: str, allowed_kinks: List[str], disabled_kinks: List[str] = None) -> str:
    """Generate task with STRICT kink filtering"""
    
    allowed_str = ", ".join(allowed_kinks) if allowed_kinks else "general submission"
    disabled_str = ", ".join(disabled_kinks) if disabled_kinks else "none"
    
    # STRICT prompt
    prompt = f"""Generate a {intensity} intensity BDSM task for a submissive.

ABSOLUTE RULES - FOLLOW EXACTLY:
1. ONLY use these ALLOWED activities: {allowed_str}
2. NEVER use these FORBIDDEN activities: {disabled_str}
3. If "Marking/Writing" or "marking" is FORBIDDEN: NO writing on body, NO sharpie markers, NO lipstick messages, NO drawing on skin, NO body writing of any kind
4. Task must be specific and completable in 30 minutes
5. Must require photo verification

Generate ONE task obeying ALL rules:"""
    
    ai_task = generate_ai_response(prompt, max_tokens=200)
    
    if ai_task:
        # Post-filter: check for forbidden content
        if disabled_kinks:
            task_lower = ai_task.lower()
            forbidden_marking = any(word in task_lower for word in [
                'write', 'writing', 'draw', 'drawing', 'marker', 'sharpie', 
                'lipstick', 'body art', 'pen', 'marker on'
            ])
            marking_disabled = any(m in ' '.join(disabled_kinks).lower() for m in ['marking', 'writing'])
            
            if forbidden_marking and marking_disabled:
                logger.warning("AI generated forbidden marking content, using filtered fallback")
                return get_filtered_fallback(intensity, allowed_kinks)
        
        return ai_task
    
    # Use filtered fallback
    return get_filtered_fallback(intensity, allowed_kinks)


def get_filtered_fallback(intensity: str, allowed_kinks: List[str]) -> str:
    """Get fallback task respecting kink settings"""
    allowed_lower = [k.lower() for k in allowed_kinks]
    
    # Categorized fallbacks - NO body writing tasks
    fallbacks = {
        'exhibitionism': [
            "Take a photo in front of a window with blinds partially open",
            "Wear something revealing under clothes and take a sneaky pic",
            "Take a risky photo in a semi-public location"
        ],
        'exposure': [
            "Expose yourself to a window for 10 seconds, photo required",
            "Take a photo with your shirt off in an unusual location"
        ],
        'bondage': [
            "Tie your wrists together with a belt or tie for 5 minutes",
            "Make a collar from a necktie and wear it for a photo",
            "Bind your ankles and take a photo of your restraint"
        ],
        'pain': [
            "Snap a rubber band on your wrist 5 times, show the result",
            "Hold an ice cube until it melts completely",
            "Pinch yourself and take a photo showing you completed it"
        ],
        'humiliation': [
            "Kneel on the floor and beg for permission out loud, photo required",
            "Take a photo of yourself in a humiliating pose",
            "Admit you are owned property and record yourself saying it"
        ],
        'degradation': [
            "Call yourself a worthless toy and take a selfie",
            "Get on all fours and take a photo from that position",
            "Take a photo with a sign saying 'Owned'"
        ],
        'edging': [
            "Edge yourself once without finishing, photo of your state required",
            "Touch yourself for exactly 3 minutes without release",
            "Bring yourself to the edge then stop, photograph your frustration"
        ],
        'service': [
            "Clean an area of your home while naked, send proof",
            "Prepare a drink and present it properly, photo required",
            "Kneel and wait in service position for 5 minutes, photo proof"
        ],
        'spanking': [
            "Give yourself 10 spanks with your hand, show the result",
            "Use a wooden spoon to spank yourself 5 times",
            "Spank yourself once for each minute of disobedience"
        ],
        'nipple': [
            "Pinch your nipples for 30 seconds, photo proof required",
            "Apply ice to your nipples and photograph the result",
            "Use clothespins if available for 2 minutes"
        ],
        'anal': [
            "Insert a finger and hold for 2 minutes, photo proof",
            "Use a toy if available for 5 minutes",
            "Prepare yourself with lube and show readiness"
        ],
        'CBT': [
            "Apply gentle pressure for 30 seconds, photo required",
            "Use ice on the area for 1 minute",
            "Tie off loosely with a shoelace for 2 minutes"
        ],
        'pet play': [
            "Get on all fours and bark/meow for the camera",
            "Eat something from a bowl on the floor, no hands",
            "Wear a collar and take a photo like a good pet"
        ],
        'sensory': [
            "Blindfold yourself and take a photo",
            "Wear earplugs and take a photo of your isolation",
            "Combine blindfold with bondage if possible"
        ],
        'temperature': [
            "Ice cube on sensitive area until melted, photo proof",
            "Cold shower for 30 seconds, before and after photo",
            "Hot wax drip if safe, or cold water shock"
        ],
        'gags': [
            "Stuff your mouth with underwear for 2 minutes",
            "Use tape to seal your lips, photo required",
            "Bite down on an object and hold it for photo"
        ],
        'feminization': [
            "Put on an article of women's clothing and photograph",
            "Apply makeup if available and send photo",
            "Pose in a feminine manner for the camera"
        ],
        'watersports': [
            "Hold for an extra 10 minutes beyond comfort, photo proof of desperation",
            "Edge while needing to go, photograph the struggle",
            "Take a photo in the bathroom showing obedience"
        ],
        'breathplay': [
            "Hold your breath for 30 seconds, video proof",
            "Breathe through a cloth restriction for 1 minute",
            "Practice controlled breathing and document"
        ],
        'roleplay': [
            "Act as a captured prisoner and take a photo",
            "Pose as a servant kneeling for inspection",
            "Play the role of property being displayed"
        ]
    }
    
    # Collect valid tasks
    valid_tasks = []
    for category, tasks in fallbacks.items():
        cat_variants = [category, category.replace('/', ' '), category.replace('_', ' ')]
        if any(var in ' '.join(allowed_lower) for var in cat_variants):
            valid_tasks.extend(tasks)
    
    # Generic tasks if nothing matches
    generic = [
        "Kneel and take a photo showing your submission",
        "Take a photo in a position of obedience",
        "Photograph yourself ready to serve",
        "Show yourself in a pose of respect"
    ]
    
    if valid_tasks:
        return random.choice(valid_tasks)
    return random.choice(generic)


def verify_photo(task_desc: str, photo_url: str) -> tuple:
    """Verify photo with AI"""
    prompt = f"""Task: {task_desc}
    
Analyze this photo:
1. Does it prove task completion? (YES/NO)
2. If NO, what's missing?
3. Brief comment

Format:
VERDICT: YES/NO
REASON: explanation
COMMENT: brief feedback"""
    
    result = generate_ai_response(prompt, max_tokens=150)
    
    if result:
        verdict = "YES" if "VERDICT: YES" in result.upper() else "NO"
        reason = ""
        comment = ""
        
        for line in result.split('\n'):
            if 'REASON:' in line:
                reason = line.split(':', 1)[1].strip()
            elif 'COMMENT:' in line:
                comment = line.split(':', 1)[1].strip()
        
        return verdict == "YES", reason, comment or "Task reviewed."
    
    return True, "", "Photo received."

# ==================== BOT HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start"""
    chat_id = update.effective_chat.id
    
    user = get_or_create_user(chat_id)
    
    welcome = f"""Welcome to DOM Bot v7.2

Your Chat ID: `{chat_id}`

Commands:
/kinks - Customize your kinks (STRICT filtering enabled)
/task - Get a new task
/status - Check status
/history - Task history
/resetowner - Clear all data

Your kinks are RESPECTED. Disabled kinks will NEVER appear."""
    
    await update.message.reply_text(welcome, parse_mode='Markdown')

async def kinks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show kink menu"""
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
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
    
    keyboard.append([InlineKeyboardButton("Done", callback_data="kinks_done")])
    
    await update.message.reply_text(
        "Your Kinks (click to toggle):\n"
        "✅ = Enabled | ❌ = Disabled (STRICTLY filtered)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle kink toggle"""
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    data = query.data
    
    if data == "kinks_done":
        await query.edit_message_text("Kinks updated! Use /task to get a task respecting your limits.")
        return
    
    kink_id = data.replace("toggle_", "")
    new_val = toggle_kink(chat_id, kink_id)
    
    # Refresh menu
    user = get_or_create_user(chat_id)
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
    
    keyboard.append([InlineKeyboardButton("Done", callback_data="kinks_done")])
    
    status = "enabled" if new_val else "disabled"
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate task with strict kink filtering"""
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    # Check existing task
    if user.get('current_task') and not user.get('task_completed'):
        await update.message.reply_text(
            f"You have an active task:\n\n{user['current_task']}\n\n"
            "Complete it before requesting a new one."
        )
        return
    
    # Get allowed and disabled kinks
    allowed_kinks = []
    disabled_kinks = []
    
    for kink_id, kink_name in KINK_CATEGORIES.items():
        if user.get(kink_id, True):
            allowed_kinks.append(kink_name)
        else:
            disabled_kinks.append(kink_name)
    
    # Determine intensity
    streak = user.get('current_streak', 0)
    if streak < 3:
        intensity = "light"
    elif streak < 7:
        intensity = "medium"
    else:
        intensity = "hard"
    
    # Generate task with BOTH lists
    task = generate_task(intensity, allowed_kinks, disabled_kinks)
    
    # Save
    update_user_fields(chat_id, {
        'current_task': task,
        'task_assigned_at': datetime.utcnow(),
        'task_completed': False,
        'photo_retry_count': 0
    })
    
    # Send
    keyboard = [[
        InlineKeyboardButton("Complete", callback_data="complete_task"),
        InlineKeyboardButton("Give Up", callback_data="give_up")
    ]]
    
    msg = f"""🔥 *New Task ({intensity.upper()})*

{task}

⏰ You have 30 minutes to complete.

Send photo proof when done."""
    
    await update.message.reply_text(
        msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Schedule timeout
    asyncio.create_task(auto_clear_task(chat_id, 30))

async def auto_clear_task(chat_id: str, timeout_minutes: int):
    """Auto-clear expired tasks"""
    await asyncio.sleep(timeout_minutes * 60)
    
    user = get_or_create_user(chat_id)
    
    if user.get('current_task') and not user.get('task_completed'):
        # Punish
        new_failed = user['total_tasks_failed'] + 1
        
        log_task_history(
            chat_id,
            user['current_task'],
            'expired',
            feedback="Task expired - 30 minutes passed"
        )
        
        update_user_fields(chat_id, {
            'total_tasks_failed': new_failed,
            'current_streak': 0,
            'points': max(0, user['points'] - 10),
            'current_task': None,
            'task_completed': False
        })

async def complete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for photo"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Send photo proof of completion.")

async def give_up_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Give up on task"""
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    log_task_history(
        chat_id,
        user.get('current_task', 'Unknown'),
        'failed',
        feedback="Gave up"
    )
    
    update_user_fields(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'points': max(0, user['points'] - 5),
        'current_task': None,
        'task_completed': False
    })
    
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Task failed. Streak broken. Use /task to try again.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify photo"""
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    if not user.get('current_task'):
        await update.message.reply_text("No active task. Use /task first.")
        return
    
    # Get photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_url = file.file_path
    
    await update.message.reply_text("Verifying...")
    
    success, reason, comment = verify_photo(user['current_task'], photo_url)
    
    if success:
        # Complete
        new_completed = user['total_tasks_completed'] + 1
        new_streak = user['current_streak'] + 1
        
        log_task_history(
            chat_id,
            user['current_task'],
            'completed',
            photo_url=photo_url,
            feedback=comment
        )
        
        update_user_fields(chat_id, {
            'total_tasks_completed': new_completed,
            'current_streak': new_streak,
            'longest_streak': max(user['longest_streak'], new_streak),
            'points': user['points'] + 20,
            'current_task': None,
            'task_completed': False,
            'photo_retry_count': 0
        })
        
        await update.message.reply_text(
            f"✅ Verified!\n\n{comment}\n\n"
            f"Streak: {new_streak} | Points: {user['points'] + 20}"
        )
    else:
        # Reject with retry
        new_retry = user.get('photo_retry_count', 0) + 1
        
        if new_retry >= 2:
            # Fail
            log_task_history(
                chat_id,
                user['current_task'],
                'failed',
                feedback=f"Failed verification: {reason}"
            )
            
            update_user_fields(chat_id, {
                'total_tasks_failed': user['total_tasks_failed'] + 1,
                'current_streak': 0,
                'points': max(0, user['points'] - 10),
                'current_task': None,
                'task_completed': False,
                'photo_retry_count': 0
            })
            
            await update.message.reply_text(
                f"❌ Failed verification twice.\n\n"
                f"Reason: {reason}\n\nTask failed."
            )
        else:
            update_user_fields(chat_id, {'photo_retry_count': new_retry})
            
            keyboard = [[
                InlineKeyboardButton("Try Again", callback_data="retry_photo"),
                InlineKeyboardButton("Give Up", callback_data="give_up_photo")
            ]]
            
            await update.message.reply_text(
                f"❌ Rejected: {reason}\n\n"
                f"Attempts left: {2 - new_retry}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def retry_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("Send a better photo.")

async def give_up_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    log_task_history(chat_id, user.get('current_task', 'Unknown'), 'failed')
    
    update_user_fields(chat_id, {
        'total_tasks_failed': user['total_tasks_failed'] + 1,
        'current_streak': 0,
        'current_task': None,
        'photo_retry_count': 0
    })
    
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.message.reply_text("Task failed. Use /task to retry.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    current = ""
    if user.get('current_task') and not user.get('task_completed'):
        current = f"\nActive Task:\n{user['current_task']}\n"
    
    msg = f"""📊 Status

Completed: {user['total_tasks_completed']}
Failed: {user['total_tasks_failed']}
Streak: {user['current_streak']} (Best: {user['longest_streak']})
Points: {user['points']}

{current}"""
    
    await update.message.reply_text(msg)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    history = get_task_history(chat_id)
    
    if not history:
        await update.message.reply_text("No history yet.")
        return
    
    msg = "📜 Recent Tasks:\n\n"
    for i, h in enumerate(history[:5], 1):
        emoji = "✅" if h['status'] == 'completed' else "❌"
        msg += f"{i}. {emoji} {h['task'][:40]}...\n"
    
    await update.message.reply_text(msg)

async def resetowner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("YES DELETE ALL", callback_data="confirm_reset"),
        InlineKeyboardButton("Cancel", callback_data="cancel_reset")
    ]]
    
    await update.message.reply_text(
        "⚠️ Delete ALL your data?\nCannot be undone!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    chat_id = update.effective_chat.id
    
    delete_all_user_data(chat_id)
    
    await update.callback_query.edit_message_text("All data deleted. Send /start to begin fresh.")

async def cancel_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Cancelled. No data deleted.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("Error occurred. Please try again.")

# ==================== MAIN ====================

def main():
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("TELEGRAM_TOKEN not set!")
    
    app = Application.builder().token(token).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("kinks", kinks_command))
    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("resetowner", resetowner_command))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(toggle_callback, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_task$"))
    app.add_handler(CallbackQueryHandler(give_up_callback, pattern="^give_up$"))
    app.add_handler(CallbackQueryHandler(retry_photo_callback, pattern="^retry_photo$"))
    app.add_handler(CallbackQueryHandler(give_up_photo_callback, pattern="^give_up_photo$"))
    app.add_handler(CallbackQueryHandler(confirm_reset_callback, pattern="^confirm_reset$"))
    app.add_handler(CallbackQueryHandler(cancel_reset_callback, pattern="^cancel_reset$"))
    
    # Messages
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Errors
    app.add_error_handler(error_handler)
    
    logger.info("DOM Bot v7.2 starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()