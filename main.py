# dombot.py
import os
os.environ.setdefault("IMAGE_MODEL", "chroma")
os.environ.setdefault("IMAGE_FALLBACKS", "lustify-v8")
os.environ.setdefault("TEXT_MODEL", "venice-uncensored-role-play")
os.environ.setdefault("IMAGE_ASPECT", "3:4")

import json, random, logging, asyncio
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ContextTypes, filters)

from core import state as st, venice, render, verify, venue, tasks as tk, prompts, storage

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "").strip()
VENICE_API_KEY = (os.getenv("VENICE_API_KEY") or "").strip()

USE_LOCATION = os.environ.get("IMAGE_USE_LOCATION", "0") == "1"
TASK_PIC_CHANCE = float(os.getenv("TASK_PIC_CHANCE", "0.3"))
REWARD_POINTS = int(os.getenv("REWARD_POINTS", "200"))

AVATAR_GENDERS = {
    "male": {"emoji": "M", "name": "Male", "desc": "masculine, muscular or slim", "lead": "man"},
    "female": {"emoji": "F", "name": "Female", "desc": "feminine, curvy or slim", "lead": "woman"},
    "trans": {"emoji": "T", "name": "Trans/Futa", "desc": "feminine with penis and breasts",
              "lead": "trans woman"},
}
AVATAR_RACES = {"white": {"emoji": "1", "name": "White/Caucasian"},
                "black": {"emoji": "2", "name": "Black/African"},
                "asian": {"emoji": "3", "name": "Asian"},
                "hispanic": {"emoji": "4", "name": "Hispanic/Latino"},
                "middle_eastern": {"emoji": "5", "name": "Middle Eastern"},
                "indian": {"emoji": "6", "name": "Indian/South Asian"}}
AVATAR_BUILDS = {"slim": {"emoji": "1", "name": "Slim", "desc": "extremely skinny, petite, waif-like"},
                 "athletic": {"emoji": "2", "name": "Athletic", "desc": "fit, toned, muscular"},
                 "curvy": {"emoji": "3", "name": "Curvy", "desc": "full figured, wide hips"},
                 "muscular": {"emoji": "4", "name": "Muscular", "desc": "ripped, bodybuilder"}}
AVATAR_HAIR = {"blonde": "Blonde", "brunette": "Brunette", "black": "Black",
               "red": "Red", "grey": "Grey", "bald": "Bald"}
AVATAR_SIZES = {
    "small": {"male": "small cock and balls", "female": "small neat breasts",
              "trans": "small cock and balls, small breasts"},
    "medium": {"male": "average cock and balls", "female": "medium breasts",
               "trans": "average cock and balls, medium breasts"},
    "large": {"male": "thick heavy cock and balls", "female": "large heavy breasts",
              "trans": "thick heavy cock and balls, large breasts"},
}
AVATAR_VARIANTS = {
    "clothed": {"label": "Clothed", "clothed": True},
    "nude": {"label": "Nude", "clothed": False},
}
GENITAL_CLAUSE = {"male": "cock and balls clearly visible",
                  "female": "pussy clearly visible, breasts bare",
                  "trans": "cock and breasts clearly visible"}

DOM_VOICE = """You are the Domme. Composed, exacting, quietly amused.
You run your sub's training. You are the boss and you both know it.

VOICE:
- Dry, clipped, unhurried. "Good." "Again." "Better."
- Short paragraphs. One to three sentences each. You're texting, not lecturing.
- Praise is earned and specific. When he fails: name it plainly, then make him do it again.
- Pet names sparingly: "pet", "sweetheart", "doll". Never stacked.

DOMINANCE:
- You decide. Risk, gear, position - you call it.
- State tasks as orders, present tense. "You're going to hold that." Not "would you like to."
- No hedging, no maybes, no questions you already know the answer to.

RULES:
- Never break character, never mention being an AI.
- Never explain the task format - just give the task.
- Keep the voice through task text too.
- Telegram markdown only, no headers. Emojis sparing."""

DOM_POSES = [
    "standing, arms folded, chin lifted",
    "seated, one leg crossed over the other, leaning back",
    "standing three quarter turn, hands on hips",
    "leaning against a wall, one ankle crossed over the other",
    "seated on the edge of a table, hands braced either side",
]
DOMINANT_OUTFITS_MALE = [
    "open black leather vest over bare chest, leather trousers",
    "bare-chested with a leather chest harness",
    "black latex trousers and a leather harness",
    "sleeveless black shirt, leather belt, leather trousers",
    "black waistcoat with no shirt, leather cuffs",
    "tight black t-shirt and leather trousers",
    "leather kilt and bare chest",
]
DOMINANT_OUTFITS_FEMALE = [
    "black latex catsuit, unzipped to the sternum",
    "black leather corset and tight trousers",
    "strappy leather harness over bare skin and a short skirt",
    "black PVC mini dress with a wide studded belt",
    "sheer black shirt over a lace bra, leather skirt",
    "red corset and thigh-high boots",
    "black bodysuit and fishnet stockings",
]
REWARD_POSES = [
    "kneeling, one knee forward, hips back",
    "kneeling upright, hands behind head, chest forward",
    "sitting back on the heels, arms overhead",
    "reclining on one elbow, top leg open, face turned to the lens",
]
REWARD_GEAR = ["nothing but a leather collar", "a leather collar and wrist cuffs",
               "a black leather collar", "a chest harness and nothing else"]

TASK_MODELS = ["chroma", "lustify-v8", "wai-illu"]
GREETINGS = ["hi", "hello", "hey", "good morning", "good evening", "hiya", "howdy"]
TASK_INQUIRIES = ["task", "my task", "current task", "what task", "any task", "status", "check task"]
COMPLIMENTS = ["beautiful", "sexy", "hot", "gorgeous", "pretty", "cute", "perfect", "love you"]
DISRESPECTFUL = ["fuck", "shit", "bitch", "stupid", "dumb", "hate", "idiot", "moron"]


def get_title(_=None):
    return "Mistress"


def avatar_gender(state):
    return state.get("avatar_gender") or state.get("gender") or "female"


def subject_clause(state):
    g = avatar_gender(state)
    race = AVATAR_RACES.get(state.get("avatar_race") or "white", AVATAR_RACES["white"])["name"].split("/")[0]
    build = AVATAR_BUILDS.get(state.get("avatar_build") or "athletic", AVATAR_BUILDS["athletic"])["desc"]
    hair = (state.get("avatar_hair") or "brunette")
    hair = AVATAR_HAIR.get(hair, hair)
    size = AVATAR_SIZES.get(state.get("avatar_genital_size") or "medium", AVATAR_SIZES["medium"])
    bits = [f"Raw editorial photograph of a striking {race} {AVATAR_GENDERS[g]['lead']}"]
    bits.append(build)
    bits.append("bald" if hair.lower() == "bald" else f"{hair.lower()} hair")
    bits.append(size.get(g, size["female"]))
    return bits


def task_keyboard(task_id, title):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Done, {title}", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton("Not possible", callback_data=f"blocked_{task_id}")],
        [InlineKeyboardButton("I can't...", callback_data=f"giveup_{task_id}")],
        [InlineKeyboardButton("Mercy", callback_data=f"mercy_{task_id}")],
    ])


def intensity_keyboard(selected=None):
    rows = []
    for key, label in (("gentle", "Gentle"), ("standard", "Standard"), ("harsh", "Harsh")):
        mark = "Y " if key == selected else ""
        rows.append([InlineKeyboardButton(f"{mark}{label}", callback_data=f"intensity_{key}")])
    return InlineKeyboardMarkup(rows)


def outfit_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(o["name"], callback_data=f"outfit_{k}")]
                                 for k, o in tk.OUTFIT_OPTIONS.items()])


def gender_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Male", callback_data="gender_male")],
                                 [InlineKeyboardButton("Female", callback_data="gender_female")],
                                 [InlineKeyboardButton("Trans", callback_data="gender_trans")],
                                 [InlineKeyboardButton("Non-binary", callback_data="gender_nonbinary")]])


def present_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(o["name"], callback_data=f"present_{k}")]
                                 for k, o in tk.CONTEXT_OPTIONS.items()])


def privacy_keyboard(selected=None):
    rows = []
    for index, (key, short, _) in enumerate(venue.PRIVACY_LEVELS, start=1):
        mark = "Y " if key == selected else ""
        rows.append([InlineKeyboardButton(f"{mark}{index}. {short}", callback_data=f"privacy_{key}")])
    return InlineKeyboardMarkup(rows)


def _privacy_prompt(state):
    current = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
        state.get("venue") or "")
    lines = "\n".join(f"{i}. {short}: {desc}"
                      for i, (_, short, desc) in enumerate(venue.PRIVACY_LEVELS, start=1))
    return (f"How much cover have you got?\n\n1 is safest, 4 is most exposed.\n\n{lines}\n\n"
            f"Currently: {venue.PRIVACY_LABELS[current]}", privacy_keyboard(current))


def kinks_keyboard(state):
    rows = [[InlineKeyboardButton(f"{tk.KINK_LEVELS[state.get(k) or 'okay']['emoji']} {n}",
                                  callback_data=f"kinkmenu_{k}")]
            for k, (n, _) in tk.KINK_CATEGORIES.items()]
    rows.append([InlineKeyboardButton("Done", callback_data="kinks_done")])
    return InlineKeyboardMarkup(rows)


def venue_keyboard():
    rows, row = [], []
    for key, label in [("home", "Home"), ("hotel", "Hotel"), ("office", "Office"),
                       ("gym", "Gym"), ("pool", "Pool"), ("beach", "Beach"),
                       ("park", "Park"), ("bar", "Bar"), ("car", "Car")]:
        row.append(InlineKeyboardButton(label, callback_data=f"venue_{key}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Somewhere else", callback_data="venue_custom")])
    return InlineKeyboardMarkup(rows)


def variant_keyboard(selected):
    return InlineKeyboardMarkup([[InlineKeyboardButton(("Y " if k == selected else "") + v["label"],
                                                      callback_data=f"variant_{k}")]
                                 for k, v in AVATAR_VARIANTS.items()])


def model_keyboard(selected, prefix="model"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(("Y " if m == selected else "") + m,
                                                      callback_data=f"{prefix}_{m}")]
                                 for m in TASK_MODELS])


def avatar_gender_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{g['emoji']} {g['name']}",
                                                      callback_data=f"av_gender_{k}")]
                                 for k, g in AVATAR_GENDERS.items()])


def avatar_race_kb():
    rows, row = [], []
    for k, r in AVATAR_RACES.items():
        row.append(InlineKeyboardButton(r["name"], callback_data=f"av_race_{k}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def avatar_build_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{b['emoji']} {b['name']}",
                                                      callback_data=f"av_build_{k}")]
                                 for k, b in AVATAR_BUILDS.items()])


def avatar_hair_kb():
    rows, row = [], []
    for k, h in AVATAR_HAIR.items():
        row.append(InlineKeyboardButton(h, callback_data=f"av_hair_{k}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def avatar_size_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(s["name"], callback_data=f"av_size_{k}")]
                                 for k, s in (("small", {"name": "Small"}), ("medium", {"name": "Medium"}),
                                              ("large", {"name": "Large"}))])


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Get a task", callback_data="menu_task")],
        [InlineKeyboardButton("Outfit", callback_data="menu_outfit"),
         InlineKeyboardButton("Location", callback_data="menu_location")],
        [InlineKeyboardButton("Avatar", callback_data="menu_avatar"),
         InlineKeyboardButton("Variant", callback_data="menu_variant")],
        [InlineKeyboardButton("Privacy", callback_data="menu_privacy"),
         InlineKeyboardButton("Intensity", callback_data="menu_intensity")],
        [InlineKeyboardButton("Kinks", callback_data="menu_kinks")],
        [InlineKeyboardButton("Schedule", callback_data="menu_schedule"),
         InlineKeyboardButton("Interval", callback_data="menu_interval")],
        [InlineKeyboardButton("Settings", callback_data="menu_settings")],
        [InlineKeyboardButton("Rewards", callback_data="menu_rewards"),
         InlineKeyboardButton("Status", callback_data="menu_status")],
    ])


def _task_header(delta, label, baseline, risk, intensity):
    bits = [f"Risk {risk}/5 ({intensity})"]
    if delta:
        bits.append(f"Exposure: {venue.PRIVACY_LABELS[label]} - was "
                    f"{venue.PRIVACY_LABELS[baseline]}")
    return "\n".join(bits) + "\n\n"


async def generate_render(state, *, nude=False, scene_extra=""):
    g = avatar_gender(state)
    spec = venice.get_spec(state.get("reward_model") if nude else state.get("task_model"), nude=nude)
    backdrop = (state.get("location_notes") or "") if USE_LOCATION else ""

    async def build():
        if nude:
            scene = ", ".join(p for p in (backdrop, scene_extra) if p)
            return prompts.build(subject_clause(state), nude=True,
                                 gear=random.choice(REWARD_GEAR),
                                 pose=random.choice(REWARD_POSES),
                                 clause=GENITAL_CLAUSE.get(g, "genitals clearly visible"),
                                 scene=scene)
        outfit = (random.choice(DOMINANT_OUTFITS_MALE) if g == "male"
                  else random.choice(DOMINANT_OUTFITS_FEMALE))
        scene = ", ".join(p for p in (scene_extra, "framed from the thighs up") if p)
        return prompts.build(subject_clause(state), nude=False,
                             outfit=outfit,
                             pose=random.choice(DOM_POSES),
                             scene=scene)

    return await render.render_best(spec, build)


async def deliver_reward(bot, user_id, *, caption, wish=""):
    state = st.get_state(user_id)
    png = await generate_render(state, nude=True, scene_extra=wish)
    verdict = await verify.nude_check(png)
    if verdict == "COVERED":
        retry = await generate_render(state, nude=True, scene_extra=wish)
        if await verify.nude_check(retry) != "COVERED":
            png = retry
    await storage.deliver(bot, user_id, user_id, png, caption=caption, prefix="reward")


async def ask_reward(update, context, user_id):
    st.get_state(user_id)["pending"] = "reward_wish"
    await update.effective_message.reply_text(
        "Reward earned. What do you want to see?",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Anything", callback_data="wish_skip")]]))


async def wish_skip_callback(update, context):
    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    st.get_state(user_id)["pending"] = None
    await q.edit_message_text("Coming up...")
    try:
        await deliver_reward(context.bot, user_id, caption="Yours.")
    except Exception:
        logger.exception("reward failed")
        await q.edit_message_text("Render failed.")


async def reward_cmd(update, context):
    await ask_reward(update, context, update.effective_user.id)


async def custom_input(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user or not msg.text:
        return
    state = st.get_state(user.id)
    pending = state.get("pending")
    if pending == "reward_wish":
        wish = msg.text.strip()[:200]
        state["pending"] = None
        await msg.reply_text("Coming up...")
        try:
            await deliver_reward(context.bot, user.id, caption="Yours.", wish=wish)
        except Exception:
            logger.exception("reward failed")
            await msg.reply_text("Render failed.")
        return
    if pending == "custom_location":
        place = msg.text.strip()[:60]
        state["venue"] = place
        state["pending"] = "wizard_privacy"
        text, markup = _privacy_prompt(state)
        await msg.reply_text(text, reply_markup=markup)
        return
    if pending == "custom_outfit":
        state["current_outfit"] = "Custom: " + msg.text.strip()[:50]
        state["outfit_detail"] = msg.text.strip()[:300]
        state["outfit_items"] = [i.strip() for i in msg.text.split(",")][:6]
        state["pending"] = None
        await msg.reply_text("Noted. Use /location.")
        return
    if pending == "outfit_detail":
        state["outfit_detail"] = msg.text.strip()[:300]
        state["pending"] = None
        await msg.reply_text("Noted.")
        return
    if pending == "interval":
        parts = msg.text.strip().lower().split()
        if len(parts) != 2:
            await msg.reply_text("Send as: MIN MAX")
            return
        try:
            lo, hi = int(parts[0]), int(parts[1])
        except ValueError:
            await msg.reply_text("Numbers only.")
            return
        if lo < 5 or hi > 1440 or lo >= hi:
            await msg.reply_text("Min 5-1440, max above min.")
            return
        state["min_interval"], state["max_interval"], state["pending"] = lo, hi, None
        await msg.reply_text(f"Interval: {lo}-{hi} minutes.")
        return
    if pending == "blocker":
        await blocker_input(update, context)
        return
    await chat_handler(update, context)


async def chat_handler(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user or not msg.text or msg.text.startswith("/"):
        return
    state = st.get_state(user.id)
    history = state.setdefault("history", [])
    history.append({"role": "user", "content": msg.text.strip()})
    state["history"] = history[-20:]
    await context.bot.send_chat_action(chat_id=msg.chat_id, action="typing")
    reply = await venice.chat(state["history"], DOM_VOICE, temperature=0.9)
    if not reply:
        reply = "Say that again."
    state["history"] = (state["history"] + [{"role": "assistant", "content": reply}])[-20:]
    await msg.reply_text(reply[:4000])


async def start_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    if not state.get("gender"):
        await update.effective_message.reply_text("First - gender:", reply_markup=gender_keyboard())
        return
    cover = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
        state.get("location") or "")
    await update.effective_message.reply_text(
        f"Back again.\n\n{state.get('location') or 'No location set'} | "
        f"{state.get('intensity') or 'standard'} | cover: {venue.PRIVACY_LABELS[cover]} | "
        f"{state.get('points') or 0}/{REWARD_POINTS} pts",
        reply_markup=main_menu())


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "/task a challenge\n/location venue and rooms\n/outfit what you're wearing\n"
        "/avatar her photo\n/reward a reward render\n"
        "/variant clothed or nude\n/privacy how much cover\n/intensity how hard\n"
        "/kinks /schedule /interval /settings /rewards /status\n/clear /reset",
        reply_markup=main_menu())


async def settings_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    cover = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
        state.get("location") or "")
    await update.effective_message.reply_text(
        f"avatar: {state.get('avatar_race') or 'unset'} {avatar_gender(state)} "
        f"{state.get('avatar_build') or ''} {state.get('avatar_hair') or ''}\n"
        f"variant: {state.get('variant') or 'clothed'}\n"
        f"cover: {venue.PRIVACY_LABELS[cover]}\n"
        f"intensity: {state.get('intensity') or 'standard'}\n"
        f"outfit: {state.get('outfit_detail') or state.get('current_outfit') or 'unset'}\n"
        f"task model: {state.get('task_model') or venice.IMAGE_MODEL}\n"
        f"reward model: {state.get('reward_model') or venice.IMAGE_MODEL_REWARD}\n"
        f"location: {state.get('location') or 'unset'}\n"
        f"task pic chance: {TASK_PIC_CHANCE}\n"
        f"reward at: {REWARD_POINTS} pts\n"
        f"points: {state.get('points') or 0} streak: {state.get('streak') or 0}",
        reply_markup=main_menu())


async def menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    route = q.data.split("_", 1)[1]
    if route == "task":
        await issue_task(update, context)
    elif route == "outfit":
        await outfit_cmd(update, context)
    elif route == "location":
        await location_cmd(update, context)
    elif route == "avatar":
        await avatar_cmd(update, context)
    elif route == "variant":
        await variant_cmd(update, context)
    elif route == "privacy":
        await privacy_cmd(update, context)
    elif route == "intensity":
        await intensity_cmd(update, context)
    elif route == "kinks":
        await kinks_cmd(update, context)
    elif route == "schedule":
        await schedule_cmd(update, context)
    elif route == "interval":
        await interval_cmd(update, context)
    elif route == "settings":
        await settings_cmd(update, context)
    elif route == "rewards":
        await rewards_cmd(update, context)
    elif route == "status":
        await status_cmd(update, context)


async def avatar_cmd(update, context):
    st.get_state(update.effective_user.id)["pending"] = None
    await update.effective_message.reply_text(
        "Build her.\n\n1/5: gender:", reply_markup=avatar_gender_kb())


async def avatar_gender_callback(update, context):
    q = update.callback_query
    await q.answer()
    g = q.data.split("_", 2)[2]
    if g not in AVATAR_GENDERS:
        await q.edit_message_text("Unknown.")
        return
    st.get_state(update.effective_user.id)["avatar_gender"] = g
    await q.edit_message_text(f"Gender: {AVATAR_GENDERS[g]['name']}\n\n2/5: race:",
                              reply_markup=avatar_race_kb())


async def avatar_race_callback(update, context):
    q = update.callback_query
    await q.answer()
    r = q.data.split("_", 2)[2]
    if r not in AVATAR_RACES:
        await q.edit_message_text("Unknown.")
        return
    st.get_state(update.effective_user.id)["avatar_race"] = r
    await q.edit_message_text(f"Race: {AVATAR_RACES[r]['name']}\n\n3/5: build:",
                              reply_markup=avatar_build_kb())


async def avatar_build_callback(update, context):
    q = update.callback_query
    await q.answer()
    b = q.data.split("_", 2)[2]
    if b not in AVATAR_BUILDS:
        await q.edit_message_text("Unknown.")
        return
    st.get_state(update.effective_user.id)["avatar_build"] = b
    await q.edit_message_text(f"Build: {AVATAR_BUILDS[b]['name']}\n\n4/5: hair:",
                              reply_markup=avatar_hair_kb())


async def avatar_hair_callback(update, context):
    q = update.callback_query
    await q.answer()
    h = q.data.split("_", 2)[2]
    if h not in AVATAR_HAIR:
        await q.edit_message_text("Unknown.")
        return
    st.get_state(update.effective_user.id)["avatar_hair"] = h
    await q.edit_message_text(f"Hair: {AVATAR_HAIR[h]}\n\n5/5: build of chest and groin:",
                              reply_markup=avatar_size_kb())


async def avatar_size_callback(update, context):
    q = update.callback_query
    await q.answer()
    s = q.data.split("_", 2)[2]
    if s not in AVATAR_SIZES:
        await q.edit_message_text("Unknown.")
        return
    user = update.effective_user
    state = st.get_state(user.id)
    state["avatar_genital_size"] = s
    state["pending"] = None
    await q.edit_message_text("Saved. Rendering...")
    try:
        png = await generate_render(state, scene_extra="three quarter shot")
    except Exception as exc:
        await context.bot.send_message(chat_id=user.id, text=f"Saved, but the render failed: {exc}")
        return
    await storage.deliver(context.bot, user.id, user.id, png, caption="", prefix="avatar")


async def variant_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text(
        f"Renders (currently {state.get('variant') or 'clothed'}):",
        reply_markup=variant_keyboard(state.get("variant")))


async def variant_callback(update, context):
    q = update.callback_query
    await q.answer()
    v = q.data.split("_", 1)[1]
    if v not in AVATAR_VARIANTS:
        await q.edit_message_text("Unknown.")
        return
    st.get_state(update.effective_user.id)["variant"] = v
    await q.edit_message_text(f"Variant: {v}.", reply_markup=variant_keyboard(v))


async def privacy_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    text, markup = _privacy_prompt(state)
    await update.effective_message.reply_text(
        text + "\nThe place sets a default. You overrule it.", reply_markup=markup)


async def privacy_callback(update, context):
    q = update.callback_query
    await q.answer()
    user = update.effective_user
    state = st.get_state(user.id)
    level = q.data.split("_", 1)[1]
    if level not in venue.PRIVACY_LABELS:
        await q.edit_message_text("Unknown level.")
        return
    state["privacy"] = level
    v = state.get("venue") or ""
    clear = InlineKeyboardMarkup([[InlineKeyboardButton("Clear", callback_data="loc_clear")]])

    if state.get("pending") == "wizard_privacy":
        state["pending"] = None
        if venue.exposure_rank(level) >= 2:
            state["context_others"] = "public"
            state["location"] = v
            await q.edit_message_text(
                f"Locked in - {venue.PRIVACY_LABELS[level]}.\n{venue.PRIVACY_DESC[level]}\n\n"
                f"{v}\n\n/task when ready.", reply_markup=clear)
            return
        await q.edit_message_text(f"{v}.\n\nWho's about?", reply_markup=present_keyboard())
        return

    await q.edit_message_text(
        f"{venue.PRIVACY_LABELS[level]}.\n{venue.PRIVACY_DESC[level]}\n\n"
        f"{state.get('location') or ''}\n\n/task when ready.", reply_markup=clear)


async def present_callback(update, context):
    q = update.callback_query
    await q.answer()
    kind = q.data.split("_", 1)[1]
    state = st.get_state(update.effective_user.id)
    state["context_others"] = kind
    state["context_alone"] = (kind == "alone")
    state["location"] = state.get("venue") or ""
    state["pending"] = None
    current = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
        state.get("venue") or "")
    await q.edit_message_text(
        f"Cover: {venue.PRIVACY_LABELS[current]}\n\n/task when ready.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Clear", callback_data="loc_clear")]]))


async def intensity_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text(
        f"How hard should these be? (currently {state.get('intensity') or 'standard'})\n\n"
        f"Gentle drops it a notch, harsh lifts it a notch. The place sets the baseline, not this.",
        reply_markup=intensity_keyboard(state.get("intensity")))


async def intensity_callback(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("_", 1)[1]
    if key not in ("gentle", "standard", "harsh"):
        await q.edit_message_text("Unknown.")
        return
    st.get_state(update.effective_user.id)["intensity"] = key
    await q.edit_message_text(f"Intensity: {key}.")


async def setreward_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text(
        f"Reward model: {state.get('reward_model') or venice.IMAGE_MODEL_REWARD}",
        reply_markup=model_keyboard(state.get("reward_model") or venice.IMAGE_MODEL_REWARD, "setreward"))


async def setreward_callback(update, context):
    q = update.callback_query
    await q.answer()
    model = q.data.split("_", 1)[1]
    if model not in venice.MODEL_EXPLICIT:
        await q.edit_message_text(f"{model} can't do the nude reward.")
        return
    st.get_state(update.effective_user.id)["reward_model"] = model
    venice.get_spec(model, nude=True)
    await q.edit_message_text(f"Reward model: {model}.")


async def model_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text(
        "Task model:", reply_markup=model_keyboard(state.get("task_model") or venice.IMAGE_MODEL))


async def model_callback(update, context):
    q = update.callback_query
    await q.answer()
    st.get_state(update.effective_user.id)["task_model"] = q.data.split("_", 1)[1]
    await q.edit_message_text("Saved.")


async def payload_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    spec = venice.get_spec(state.get("task_model"))
    prompt, negative = prompts.build(subject_clause(state), nude=False,
                                     outfit=random.choice(DOMINANT_OUTFITS_FEMALE),
                                     pose=DOM_POSES[0],
                                     scene="framed from the thighs up")
    await update.effective_message.reply_text(
        f"model: {spec['model']}\nbox: {spec['width']}x{spec['height']}\nsteps: {spec['steps']}\n\n"
        f"positive:\n{prompt}\n\nnegative:\n{negative}"[:4000])


async def imgmodels_cmd(update, context):
    try:
        data = await venice.get("/models?type=image")
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")
        return
    await update.effective_message.reply_text(
        ("\n".join(i.get("id", "?") for i in data.get("data", [])) or "empty")[:4000])


async def location_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    state["venue"] = None
    state["venue_typical"] = None
    state["pending"] = None
    await update.effective_message.reply_text("Where are we shooting?", reply_markup=venue_keyboard())


async def venue_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    if q.data == "venue_custom":
        state["pending"] = "custom_location"
        await q.edit_message_text("Name the place.")
        return
    state["venue"] = q.data.split("_", 1)[1]
    state["pending"] = "wizard_privacy"
    text, markup = _privacy_prompt(state)
    await q.edit_message_text(text, reply_markup=markup)


async def clear_location(update, context):
    state = st.get_state(update.effective_user.id)
    for k in ("location", "location_notes", "rooms", "probes", "venue", "features", "venue_typical", "room_pool"):
        state[k] = None if k in ("location", "location_notes", "venue", "venue_typical") else []
    state["pending"] = None
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Cleared.")
    else:
        await update.effective_message.reply_text("Cleared.")


async def gender_cmd(update, context):
    await update.effective_message.reply_text("Gender:", reply_markup=gender_keyboard())


async def gender_callback(update, context):
    q = update.callback_query
    await q.answer()
    st.get_state(update.effective_user.id)["gender"] = q.data.split("_", 1)[1]
    await q.edit_message_text("Saved.", reply_markup=main_menu())


async def outfit_cmd(update, context):
    await update.effective_message.reply_text("What are you wearing?", reply_markup=outfit_keyboard())


async def outfit_callback(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("_", 1)[1]
    state = st.get_state(update.effective_user.id)
    if key == "custom":
        state["pending"] = "custom_outfit"
        await q.edit_message_text("Describe it.")
        return
    opt = tk.OUTFIT_OPTIONS[key]
    state["current_outfit"] = opt["name"]
    state["outfit_items"] = opt.get(f"{state.get('gender') or 'male'}_items", opt["male_items"])
    state["pending"] = "outfit_detail"
    await q.edit_message_text(f"{opt['name']}, roughly. What are you actually in? Type it or /skip.")


async def kinks_cmd(update, context):
    await update.effective_message.reply_text(
        "Kinks\n\nX no | O okay | Y desired\n\nTap to change:",
        reply_markup=kinks_keyboard(st.get_state(update.effective_user.id)))


async def kink_menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("_", 1)[1]
    state = st.get_state(update.effective_user.id)
    cur = state.get(key) or "okay"
    rows = [[InlineKeyboardButton(("Y " if cur == lv else "") + f"{tk.KINK_LEVELS[lv]['emoji']} {tk.KINK_LEVELS[lv]['name']}",
                                  callback_data=f"kinkset_{key}_{lv}")] for lv in ("no", "okay", "yes")]
    rows.append([InlineKeyboardButton("Back", callback_data="kinks_back")])
    await q.edit_message_text(f"{tk.KINK_CATEGORIES[key][0]}\n\n{tk.KINK_CATEGORIES[key][1]}\n\nCurrent: {cur}",
                              reply_markup=InlineKeyboardMarkup(rows))


async def kink_set_callback(update, context):
    q = update.callback_query
    await q.answer()
    key, lv = q.data.replace("kinkset_", "").rsplit("_", 1)
    state = st.get_state(update.effective_user.id)
    state[key] = lv
    await q.edit_message_text(f"{tk.KINK_CATEGORIES[key][0]} = {lv}", reply_markup=kinks_keyboard(state))


async def kinks_back_callback(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Kinks:", reply_markup=kinks_keyboard(st.get_state(update.effective_user.id)))


async def kinks_done_callback(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Saved.", reply_markup=main_menu())


async def skip_cmd(update, context):
    st.get_state(update.effective_user.id)["pending"] = None
    await update.effective_message.reply_text("Fine. /task.")


async def interval_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    state["pending"] = "interval"
    await update.effective_message.reply_text(
        f"Current: {state.get('min_interval')}-{state.get('max_interval')}. Send MIN MAX.")


async def schedule_cmd(update, context):
    await update.effective_message.reply_text("Auto tasks:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Enable", callback_data="sched_on")],
        [InlineKeyboardButton("Disable", callback_data="sched_off")]]))


async def schedule_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    if q.data == "sched_on":
        state["scheduling_enabled"] = True
        state["next_task_time"] = datetime.now(timezone.utc) + timedelta(
            minutes=random.randint(state.get("min_interval") or 30, state.get("max_interval") or 180))
        await q.edit_message_text("On.")
    else:
        state["scheduling_enabled"] = False
        state["next_task_time"] = None
        await q.edit_message_text("Off.")


async def issue_task(update, context, label="TASK"):
    user = update.effective_user
    state = st.get_state(user.id)
    session = st.get_session()
    try:
        if not state.get("gender"):
            await gender_cmd(update, context)
            return
        if not state.get("current_outfit"):
            await outfit_cmd(update, context)
            return
        if not state.get("location"):
            await location_cmd(update, context)
            return
        if session.query(st.Task).filter_by(user_id=user.id, status="pending").first():
            await update.effective_message.reply_text("You already have one pending.")
            return
        await update.effective_message.reply_text("Writing...")
        try:
            text, risk, delta, exposure = await tk.generate_task_text(
                state, session, voice=DOM_VOICE)
        except Exception as exc:
            logger.exception("task generation failed")
            await update.effective_message.reply_text(
                f"Couldn't write that one - {type(exc).__name__}: {exc}")
            return
        now = datetime.now(timezone.utc)
        task = st.Task(user_id=user.id, task_text=text, risk_level=risk, created_at=now,
                       exposure=delta, exposure_label=exposure,
                       expires_at=now + timedelta(minutes=30))
        session.add(task)
        session.commit()
        context.job_queue.run_once(expire_task, when=timedelta(minutes=30),
                                   data={"user_id": user.id, "task_id": task.id})
        base = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
            state.get("location") or "")
        note = _task_header(delta, exposure, base, risk, state.get("intensity") or "standard")
        await update.effective_message.reply_text(
            f"{label}\n\n{note}{text}\n\n30 minutes.", reply_markup=task_keyboard(task.id, get_title()))
        if random.random() < TASK_PIC_CHANCE:
            try:
                png = await generate_render(state)
                await storage.deliver(context.bot, user.id, user.id, png,
                                      caption="This is what's waiting for you.", prefix="avatar")
            except Exception:
                logger.warning("pre-task avatar failed")
    finally:
        session.close()


async def task_cmd(update, context):
    context.user_data.pop("blocked_task_id", None)
    await issue_task(update, context)


async def status_cmd(update, context):
    session = st.get_session()
    try:
        active = session.query(st.Task).filter_by(user_id=update.effective_user.id, status="pending").first()
        if not active:
            await update.effective_message.reply_text("Nothing pending. /task")
            return
        left = (active.expires_at - datetime.now(timezone.utc)).total_seconds() / 60
        extra = f"\n\nNeeds: {active.followup_target}" if active.followup_target else ""
        exposure = f"\nExposure: {active.exposure_label}" if active.exposure else ""
        await update.effective_message.reply_text(
            f"{max(0, left):.0f} min left{exposure}\n\n{active.task_text[:200]}{extra}",
            reply_markup=task_keyboard(active.id, get_title()))
    finally:
        session.close()


async def rewards_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    pts = state.get("points") or 0
    left = max(0, REWARD_POINTS - pts)
    await update.effective_message.reply_text(
        f"Rewards fire on their own at {REWARD_POINTS} points, then take {REWARD_POINTS} back.\n\n"
        f"Points: {pts}\n{left} to go.\n\n/reward triggers one now without spending.")


async def complete_callback(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Send the photo.")


async def blocked_callback(update, context):
    q = update.callback_query
    await q.answer()
    try:
        st.get_state(update.effective_user.id)["pending"] = "blocker"
        await q.edit_message_text("What's in the way?")
    except Exception:
        logger.exception("blocked prompt failed")
        await context.bot.send_message(chat_id=update.effective_user.id, text="What's in the way?")


async def blocker_input(update, context):
    user = update.effective_user
    state = st.get_state(user.id)
    state["pending"] = None
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(user_id=user.id, status="pending").first()
        if not task:
            await update.effective_message.reply_text("Gone. /task")
            return
        if task.blocked_count >= 3:
            await update.effective_message.reply_text("Three reworks. Use Mercy.")
            return
        text = update.effective_message.text.strip()[:200]
        loc = state.get("location") or "Unknown"
        norm = text.lower().strip().rstrip(".")
        existing = None
        for c in session.query(st.LocationConstraint).filter_by(user_id=user.id, location=loc).all():
            if c.constraint.lower().strip().rstrip(".") == norm:
                existing = c
                break
        now = datetime.now(timezone.utc)
        if existing:
            existing.times_hit += 1
            existing.expires_at = now + timedelta(days=30 if existing.times_hit >= 2 else 3)
        else:
            session.add(st.LocationConstraint(user_id=user.id, location=loc, constraint=text,
                                              expires_at=now + timedelta(hours=3)))
        session.commit()
        if venue.is_no_cover(text):
            await update.effective_message.reply_text("No cover. Dropping it down.")
        else:
            await update.effective_message.reply_text("Fine. Again.")
        try:
            new, risk, delta, exposure = await tk.generate_task_text(state, session, voice=DOM_VOICE)
        except Exception as exc:
            logger.exception("rework generation failed")
            await update.effective_message.reply_text(f"Couldn't rework - {type(exc).__name__}: {exc}")
            return
        task.task_text, task.risk_level = new, risk
        task.exposure, task.exposure_label = delta, exposure
        task.verification_attempts, task.followup_target = 0, None
        task.expires_at = now + timedelta(minutes=30)
        task.blocked_count += 1
        session.commit()
        base = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(loc)
        note = _task_header(delta, exposure, base, risk, state.get("intensity") or "standard")
        await update.effective_message.reply_text(
            f"REWORKED\n\n{note}{new}\n\n30 minutes.", reply_markup=task_keyboard(task.id, get_title()))
    finally:
        session.close()


async def mercy_callback(update, context):
    q = update.callback_query
    await q.answer()
    user = update.effective_user
    state = st.get_state(user.id)
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(id=int(q.data.split("_", 1)[1]),
                                                user_id=user.id, status="pending").first()
        if not task:
            await q.edit_message_text("Nothing pending.")
            return
        await q.edit_message_text("Fine. Something else...")
        try:
            new, risk, delta, exposure = await tk.generate_task_text(state, session, voice=DOM_VOICE)
        except Exception as exc:
            logger.exception("mercy generation failed")
            await context.bot.send_message(chat_id=user.id,
                                           text=f"Couldn't write one - {type(exc).__name__}: {exc}")
            return
        now = datetime.now(timezone.utc)
        task.task_text, task.risk_level = new, risk
        task.exposure, task.exposure_label = delta, exposure
        task.verification_attempts, task.followup_target = 0, None
        task.expires_at = now + timedelta(minutes=30)
        session.commit()
        base = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
            state.get("location") or "")
        note = _task_header(delta, exposure, base, risk, state.get("intensity") or "standard")
        await context.bot.send_message(chat_id=user.id, text=f"NEW\n\n{note}{new}\n\n30 minutes.",
                                       reply_markup=task_keyboard(task.id, get_title()))
    finally:
        session.close()


async def giveup_callback(update, context):
    q = update.callback_query
    await q.answer()
    user = update.effective_user
    state = st.get_state(user.id)
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(id=int(q.data.split("_", 1)[1]), user_id=user.id).first()
        if task and task.status == "pending":
            task.status = "failed"
            task.followup_target = None
            state["points"] = max(0, (state.get("points") or 0) - 5)
            state["streak"] = 0
            session.commit()
            await q.edit_message_text("Abandoned. -5.")
    finally:
        session.close()


async def retry_callback(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Send the retry.")


async def handle_photo(update, context):
    user = update.effective_user
    state = st.get_state(user.id)
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(user_id=user.id, status="pending").first()
        photo = update.message.photo[-1]
        await update.message.reply_text("Checking...")
        data = bytes(await (await context.bot.get_file(photo.file_id)).download_as_bytearray())
        if len(data) < 1000:
            await update.message.reply_text("Too small.")
            return
        kind = "verification" if task else "user_upload"
        up = await storage.upload(data, user.id, image_type=kind)
        session.add(st.UserImage(user_id=user.id, telegram_file_id=photo.file_id, image_type=kind,
                                 cloudinary_url=up["url"] if up else None,
                                 cloudinary_public_id=up["public_id"] if up else None))
        session.commit()
        if not task:
            await update.message.reply_text("Saved.")
            return
        now = datetime.now(timezone.utc)
        if now > task.expires_at:
            task.status = "expired"
            session.commit()
            await update.message.reply_text("Expired. /task")
            return
        public = venue.exposure_rank(task.exposure or "") >= 2
        verdict = await verify.verify_photo(data, task.task_text, task.followup_target,
                                            public=public)
        if verdict is None:
            await update.message.reply_text("Verifier down - resend, no attempt used.")
            return
        verified, missing, reason = verdict
        if reason == "Verifier returned nothing":
            await update.message.reply_text("Verifier came back empty - send it again, that one didn't count.")
            return
        task.verification_attempts += 1
        task.sharpness = int(await asyncio.to_thread(render.sharpness_score, data))
        if up:
            task.cloudinary_url, task.cloudinary_public_id = up["url"], up["public_id"]

        if verified == "yes":
            gain = 10 * task.risk_level
            task.status, task.completed_at, task.photo_url = "completed", now, photo.file_id
            task.followup_target = None
            context.user_data.pop("blocked_task_id", None)
            state["points"] = (state.get("points") or 0) + gain
            state["streak"] = (state.get("streak") or 0) + 1
            state["completed_tasks"] = (state.get("completed_tasks") or 0) + 1
            due = (state.get("points") or 0) >= REWARD_POINTS
            if due:
                state["points"] = max(0, (state.get("points") or 0) - REWARD_POINTS)
            session.commit()
            await update.message.reply_text(
                f"+{gain}. Streak {state['streak']}. {state.get('points') or 0} pts.")
            if due:
                await ask_reward(update, context, user.id)
            return

        if task.verification_attempts >= 3:
            task.status = "failed"
            task.followup_target = None
            state["consecutive_failures"] = (state.get("consecutive_failures") or 0) + 1
            session.commit()
            await update.message.reply_text(f"Failed. {reason}")
            return

        left = 3 - task.verification_attempts
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Try Again", callback_data=f"retry_{task.id}"),
            InlineKeyboardButton("Give Up", callback_data=f"giveup_{task.id}")]])
        if missing:
            task.followup_target = missing
            session.commit()
            await update.message.reply_text(
                f"Can't see {missing}. One photo of just {missing} - close in, nothing else in frame.\n\n"
                f"{left} {'try' if left == 1 else 'tries'} left.", reply_markup=keyboard)
        else:
            task.followup_target = None
            session.commit()
            await update.message.reply_text(
                f"No - {reason}\n\nReshoot it so the task is obvious.\n\n"
                f"{left} {'try' if left == 1 else 'tries'} left.", reply_markup=keyboard)
    except Exception:
        logger.exception("photo failed")
        await update.message.reply_text("Error with that photo.")
    finally:
        session.close()


async def expire_task(context):
    user_id, task_id = context.job.data["user_id"], context.job.data["task_id"]
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(id=task_id).first()
        if not task or task.status != "pending":
            return
        task.status = "expired"
        state = st.get_state(user_id)
        state["points"] = max(0, (state.get("points") or 0) - 10)
        state["streak"] = 0
        state["consecutive_failures"] = (state.get("consecutive_failures") or 0) + 1
        session.commit()
        await context.bot.send_message(chat_id=user_id, text="Time's up. -10.")
    except Exception:
        logger.exception("expire failed")
    finally:
        session.close()


async def avatar_render_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text("One sec...")
    try:
        png = await generate_render(state, scene_extra="three quarter shot")
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")
        return
    await storage.deliver(context.bot, update.effective_chat.id, update.effective_user.id, png,
                          caption="", prefix="avatar")


async def debugavatar_cmd(update, context):
    user = update.effective_user
    await update.effective_message.reply_text("Rendering...")
    try:
        png = await generate_render(st.get_state(user.id))
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")
        return
    await render.debug_send(context.bot, png, label="avatar", chat_id=user.id, upscale_pass=True)


async def tryn_cmd(update, context):
    user = update.effective_user
    await update.effective_message.reply_text("Batch...")
    try:
        png = await generate_render(st.get_state(user.id))
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")
        return
    await render.debug_send(context.bot, png, label="tryn", chat_id=user.id, upscale_pass=True)


async def testreward_cmd(update, context):
    user = update.effective_user
    await update.effective_message.reply_text("Reward batch...")
    try:
        png = await generate_render(st.get_state(user.id), nude=True)
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")
        return
    gate = await verify.nude_check(png)
    await render.debug_send(context.bot, png, label="testreward", chat_id=user.id,
                            upscale_pass=True, gate=gate)


async def reset_cmd(update, context):
    uid = update.effective_user.id
    state = st.get_state(uid)
    state["variant"] = "clothed"
    state["privacy"] = "alone"
    state["intensity"] = "standard"
    state["location"] = None
    state["location_notes"] = None
    state["venue_typical"] = None
    state["avatar_gender"] = None
    state["avatar_race"] = None
    state["avatar_build"] = None
    state["avatar_hair"] = None
    state["avatar_genital_size"] = None
    st.drop_state(uid)
    await update.effective_message.reply_text("Defaults restored.")


async def scheduled_check(context):
    session = st.get_session()
    try:
        now = datetime.now(timezone.utc)
        session.query(st.LocationConstraint).filter(st.LocationConstraint.expires_at < now).delete()
        session.commit()
        due = session.query(st.UserState).filter(st.UserState.scheduling_enabled == True,
                                                 st.UserState.next_task_time <= now).all()
        for row in due:
            if session.query(st.Task).filter_by(user_id=row.user_id, status="pending").first():
                continue
            state = st.get_state(row.user_id)
            if not state.get("gender") or not state.get("location"):
                state["next_task_time"] = now + timedelta(minutes=15)
                continue
            try:
                text, risk, delta, exposure = await tk.generate_task_text(
                    state, session, voice=DOM_VOICE)
            except Exception:
                logger.exception(f"auto task generation failed for {row.user_id}")
                state["next_task_time"] = now + timedelta(minutes=15)
                continue
            task = st.Task(user_id=row.user_id, task_text=text, risk_level=risk, created_at=now,
                           exposure=delta, exposure_label=exposure,
                           expires_at=now + timedelta(minutes=30))
            session.add(task)
            state["next_task_time"] = now + timedelta(
                minutes=random.randint(state.get("min_interval") or 30, state.get("max_interval") or 180))
            session.commit()
            context.job_queue.run_once(expire_task, when=timedelta(minutes=30),
                                       data={"user_id": row.user_id, "task_id": task.id})
            base = venue.normalise_privacy(state.get("privacy")) or venue.privacy_default(
                state.get("location") or "")
            note = _task_header(delta, exposure, base, risk, state.get("intensity") or "standard")
            await context.bot.send_message(chat_id=row.user_id,
                                           text=f"AUTO\n\n{note}{text}\n\n30 minutes.",
                                           reply_markup=task_keyboard(task.id, get_title()))
            await asyncio.sleep(1)
    except Exception:
        logger.exception("scheduled check failed")
    finally:
        session.close()


async def error_handler(update, context):
    logger.exception("handler error", exc_info=context.error)


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN empty")
    if not VENICE_API_KEY:
        raise SystemExit("VENICE_API_KEY empty")
    st.ensure_schema()
    venice.load_specs()
    storage.configure()

    app = Application.builder().token(TOKEN).read_timeout(180).write_timeout(180).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("menu", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("variant", variant_cmd))
    app.add_handler(CommandHandler("privacy", privacy_cmd))
    app.add_handler(CommandHandler("intensity", intensity_cmd))
    app.add_handler(CommandHandler("risk", intensity_cmd))
    app.add_handler(CommandHandler("setreward", setreward_cmd))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("payload", payload_cmd))
    app.add_handler(CommandHandler("imgmodels", imgmodels_cmd))
    app.add_handler(CommandHandler("location", location_cmd))
    app.add_handler(CommandHandler("clear", clear_location))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("avatar", avatar_cmd))
    app.add_handler(CommandHandler("render", avatar_render_cmd))
    app.add_handler(CommandHandler("reward", reward_cmd))
    app.add_handler(CommandHandler("debugavatar", debugavatar_cmd))
    app.add_handler(CommandHandler("tryn", tryn_cmd))
    app.add_handler(CommandHandler("testreward", testreward_cmd))
    app.add_handler(CommandHandler("skip", skip_cmd))
    app.add_handler(CommandHandler("gender", gender_cmd))
    app.add_handler(CommandHandler("outfit", outfit_cmd))
    app.add_handler(CommandHandler("kinks", kinks_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("rewards", rewards_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("interval", interval_cmd))

    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(wish_skip_callback, pattern="^wish_skip$"))
    app.add_handler(CallbackQueryHandler(avatar_gender_callback, pattern="^av_gender_"))
    app.add_handler(CallbackQueryHandler(avatar_race_callback, pattern="^av_race_"))
    app.add_handler(CallbackQueryHandler(avatar_build_callback, pattern="^av_build_"))
    app.add_handler(CallbackQueryHandler(avatar_hair_callback, pattern="^av_hair_"))
    app.add_handler(CallbackQueryHandler(avatar_size_callback, pattern="^av_size_"))
    app.add_handler(CallbackQueryHandler(venue_callback, pattern="^venue_"))
    app.add_handler(CallbackQueryHandler(clear_location, pattern="^loc_clear$"))
    app.add_handler(CallbackQueryHandler(present_callback, pattern="^present_"))
    app.add_handler(CallbackQueryHandler(variant_callback, pattern="^variant_"))
    app.add_handler(CallbackQueryHandler(privacy_callback, pattern="^privacy_"))
    app.add_handler(CallbackQueryHandler(intensity_callback, pattern="^intensity_"))
    app.add_handler(CallbackQueryHandler(setreward_callback, pattern="^setreward_"))
    app.add_handler(CallbackQueryHandler(model_callback, pattern="^model_"))
    app.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    app.add_handler(CallbackQueryHandler(outfit_callback, pattern="^outfit_"))
    app.add_handler(CallbackQueryHandler(kink_menu_callback, pattern="^kinkmenu_"))
    app.add_handler(CallbackQueryHandler(kink_set_callback, pattern="^kinkset_"))
    app.add_handler(CallbackQueryHandler(kinks_back_callback, pattern="^kinks_back$"))
    app.add_handler(CallbackQueryHandler(kinks_done_callback, pattern="^kinks_done$"))
    app.add_handler(CallbackQueryHandler(complete_callback, pattern="^complete_"))
    app.add_handler(CallbackQueryHandler(blocked_callback, pattern="^blocked_"))
    app.add_handler(CallbackQueryHandler(giveup_callback, pattern="^giveup_"))
    app.add_handler(CallbackQueryHandler(retry_callback, pattern="^retry_"))
    app.add_handler(CallbackQueryHandler(mercy_callback, pattern="^mercy_"))
    app.add_handler(CallbackQueryHandler(schedule_callback, pattern="^sched_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_input))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(error_handler)

    app.job_queue.run_repeating(scheduled_check, interval=60, first=10,
                                job_kwargs={"misfire_grace_time": 180, "coalesce": True, "max_instances": 1})
    logger.info("dombot up")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()