#!/usr/bin/env python3
"""
DOMBot - Telegram Bot with Venice AI Integration
Debug version with full logging
"""

import os
import logging
import random
import hashlib
import json
import requests
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ============ CONFIGURATION ============

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VENICE_API_KEY = os.getenv("VENICE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set!")
if not VENICE_API_KEY:
    logger.warning("VENICE_API_KEY not set - AI features won't work!")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set!")

# ============ DATABASE SETUP ============

Base = declarative_base()

class TaskHistory(Base):
    __tablename__ = 'task_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    task_description = Column(Text, nullable=False)
    task_category = Column(String(50))
    task_hash = Column(String(32))
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<TaskHistory(id={self.id}, user={self.user_id}, desc='{self.task_description[:30]}...')>"

class UserState(Base):
    __tablename__ = 'user_state'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    chat_id = Column(Integer, nullable=False)
    current_task_id = Column(Integer, nullable=True)
    task_history_json = Column(Text, default='[]')  # Store recent task types
    
    def get_recent_tasks(self):
        try:
            return json.loads(self.task_history_json) if self.task_history_json else []
        except:
            return []
    
    def add_task_type(self, task_type):
        tasks = self.get_recent_tasks()
        tasks.append(task_type)
        self.task_history_json = json.dumps(tasks[-10:])  # Keep last 10

# Create engine and session
engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine)

# Create tables
Base.metadata.create_all(engine)

# ============ AI SERVICE ============

CREATIVE_FALLBACKS = [
    "Describe your current surroundings in vivid sensory detail.",
    "Write a short poem about your current mood.",
    "List three things you can see, hear, and feel right now.",
    "Create a character based on the last person you spoke to.",
    "Describe your ideal day from start to finish.",
    "Write a letter to your future self one year from now.",
    "Create a metaphor for how you're feeling today.",
    "Describe a color without naming it.",
    "Invent a new word and define it.",
    "Tell a story in exactly 50 words.",
]

TASK_CATEGORIES = ["position", "physical", "degradation", "exposure", "creative", "reflective"]


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    except:
        db.close()
        raise


def build_messages(user_state: UserState, category: str, db: Session) -> list:
    """Build message context for AI"""
    recent_tasks = db.query(TaskHistory).filter(
        TaskHistory.user_id == user_state.user_id
    ).order_by(TaskHistory.created_at.desc()).limit(5).all()
    
    recent_descriptions = [t.task_description for t in recent_tasks if t.task_description != "Speak clearly, pet."]
    
    messages = [
        {
            "role": "system",
            "content": """You are a creative task generator for a BDSM lifestyle app.
            Generate unique, specific, actionable tasks.
            Tasks should be creative, engaging, and contextually appropriate.
            Avoid generic instructions - make each task specific and interesting.
            Respond with ONLY the task description, no preamble."""
        }
    ]
    
    if recent_descriptions:
        messages.append({
            "role": "user",
            "content": f"Recent tasks given (avoid repeating these): {recent_descriptions}"
        })
    
    messages.append({
        "role": "user",
        "content": f"Generate a creative {category} task. Be specific and unique."
    })
    
    return messages


def generate_task_with_ai(user_state: UserState, category: str, db: Session) -> dict:
    """
    Generate a creative task using Venice AI.
    DEBUG VERSION with full logging.
    """
    logger.info("=" * 60)
    logger.info("GENERATING TASK WITH VENICE AI")
    logger.info("=" * 60)
    
    # Check API key
    if not VENICE_API_KEY:
        logger.error("VENICE_API_KEY is not set!")
        return {
            "description": random.choice(CREATIVE_FALLBACKS),
            "category": category,
            "hash": "fallback_no_key"
        }
    
    messages = build_messages(user_state, category, db)
    
    logger.info(f"Messages: {json.dumps(messages, indent=2)}")
    
    try:
        response = requests.post(
            "https://api.venice.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 300
            },
            timeout=30,
        )
        
        logger.info(f"Status Code: {response.status_code}")
        logger.info(f"Response: {response.text[:500]}")
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            
            # Generate hash
            task_hash = hashlib.md5(content.encode()).hexdigest()[:16]
            
            logger.info(f"SUCCESS! Generated: {content[:100]}...")
            logger.info("=" * 60)
            
            return {
                "description": content,
                "category": category,
                "hash": task_hash
            }
        
        # Log error details
        error_msg = "Unknown error"
        try:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", response.text)
        except:
            error_msg = response.text
        
        logger.error(f"API Error {response.status_code}: {error_msg}")
        
        # Use creative fallback
        fallback = random.choice(CREATIVE_FALLBACKS)
        return {
            "description": fallback,
            "category": category,
            "hash": hashlib.md5(fallback.encode()).hexdigest()[:16],
            "error": f"API {response.status_code}: {error_msg}"
        }
        
    except requests.exceptions.Timeout:
        logger.error("Venice API Timeout")
        fallback = random.choice(CREATIVE_FALLBACKS)
        return {
            "description": fallback,
            "category": category,
            "hash": hashlib.md5(fallback.encode()).hexdigest()[:16],
            "error": "Timeout"
        }
        
    except Exception as e:
        logger.error(f"Exception: {e}", exc_info=True)
        fallback = random.choice(CREATIVE_FALLBACKS)
        return {
            "description": fallback,
            "category": category,
            "hash": hashlib.md5(fallback.encode()).hexdigest()[:16],
            "error": str(e)
        }


def save_task_to_history(user_id: int, task_data: dict, db: Session) -> TaskHistory:
    """Save generated task to database"""
    task = TaskHistory(
        user_id=user_id,
        task_description=task_data["description"],
        task_category=task_data["category"],
        task_hash=task_data["hash"],
        completed=False
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_or_create_user(user_id: int, chat_id: int, db: Session) -> UserState:
    """Get or create user state"""
    user = db.query(UserState).filter(UserState.user_id == user_id).first()
    if not user:
        user = UserState(user_id=user_id, chat_id=chat_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ============ TELEGRAM HANDLERS ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    db = get_db()
    try:
        user = get_or_create_user(user_id, chat_id, db)
        
        await update.message.reply_text(
            "Welcome! I'm your creative task bot.\n\n"
            "Commands:\n"
            "/task - Get a new creative task\n"
            "/history - View your task history\n"
            "/complete - Mark current task complete\n"
            "/debug - Test AI connection"
        )
    finally:
        db.close()


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send a new task"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    db = get_db()
    try:
        user = get_or_create_user(user_id, chat_id, db)
        
        # Pick a random category
        category = random.choice(TASK_CATEGORIES)
        
        # Generate task with AI
        await update.message.reply_text("Generating your creative task...")
        
        task_data = generate_task_with_ai(user, category, db)
        
        # Save to history
        task_record = save_task_to_history(user_id, task_data, db)
        
        # Update user state
        user.current_task_id = task_record.id
        user.add_task_type(category)
        db.commit()
        
        # Format response
        error_note = ""
        if "error" in task_data:
            error_note = f"\n\n⚠️ Note: AI service had an issue ({task_data['error']}), using fallback."
        
        response = (
            f"🎯 **New Task - {category.upper()}**\n\n"
            f"{task_data['description']}\n\n"
            f"Reply with /complete when done, or /task for a new one."
            f"{error_note}"
        )
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in task_command: {e}", exc_info=True)
        await update.message.reply_text("Sorry, something went wrong. Try again!")
    finally:
        db.close()


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show task history"""
    user_id = update.effective_user.id
    
    db = get_db()
    try:
        tasks = db.query(TaskHistory).filter(
            TaskHistory.user_id == user_id
        ).order_by(TaskHistory.created_at.desc()).limit(10).all()
        
        if not tasks:
            await update.message.reply_text("No task history yet!")
            return
        
        msg = "*Your Recent Tasks:*\n\n"
        for t in tasks:
            status = "✅" if t.completed else "⏳"
            desc = t.task_description[:50] + "..." if len(t.task_description) > 50 else t.task_description
            msg += f"{status} *{t.task_category or 'task'}*: {desc}\n"
            msg += f"   _{t.created_at.strftime('%Y-%m-%d')}_\n\n"
        
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    finally:
        db.close()


async def complete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark current task as complete"""
    user_id = update.effective_user.id
    
    db = get_db()
    try:
        user = db.query(UserState).filter(UserState.user_id == user_id).first()
        
        if not user or not user.current_task_id:
            await update.message.reply_text("No active task to complete!")
            return
        
        task = db.query(TaskHistory).filter(TaskHistory.id == user.current_task_id).first()
        if task:
            task.completed = True
            user.current_task_id = None
            db.commit()
            await update.message.reply_text("✅ Task marked complete! Great job!")
        else:
            await update.message.reply_text("Couldn't find that task.")
            
    finally:
        db.close()


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug AI connection"""
    await update.message.reply_text("Testing Venice AI connection...")
    
    logger.info("=" * 60)
    logger.info("DEBUG COMMAND - TESTING VENICE API")
    logger.info("=" * 60)
    
    if not VENICE_API_KEY:
        await update.message.reply_text("❌ VENICE_API_KEY not set!")
        return
    
    try:
        response = requests.post(
            "https://api.venice.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-opus-4-8-fast",
                "messages": [{"role": "user", "content": "Say 'Venice AI is working!'"}],
                "temperature": 0.9,
                "max_tokens": 100
            },
            timeout=30
        )
        
        logger.info(f"Status: {response.status_code}")
        logger.info(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            await update.message.reply_text(f"✅ Venice AI is working!\n\nResponse: {content}")
        else:
            await update.message.reply_text(f"❌ API Error {response.status_code}:\n{response.text[:500]}")
            
    except Exception as e:
        logger.error(f"Debug error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    # You can add conversation handling here
    await update.message.reply_text("Use /task to get a creative challenge!")


# ============ MAIN ============

def main():
    """Start the bot"""
    logger.info("Starting DOMBot...")
    logger.info(f"VENICE_API_KEY present: {bool(VENICE_API_KEY)}")
    
    # Build application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("task", task_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("complete", complete_command))
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run
    logger.info("Bot is running!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()