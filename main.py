# dombot.py
import os
os.environ.setdefault("IMAGE_MODEL", "nano-banana-pro")
os.environ.setdefault("IMAGE_FALLBACKS", "chroma")
os.environ.setdefault("TEXT_MODEL", "claude-opus-4-8-fast")
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

DOM_VOICE = """You are a playful but demanding Domme. Speak with confidence, occasional teasing,
and personality. Be conversational, use pet names, mix encouragement with demands. Never mention
being an AI. Telegram markdown only, no headers."""

STUDIO_TITLE = {"male": "Sir", "female": "Mistress", "trans": "Mistress", "nonbinary": "Mistress"}

AVATAR_GENDERS = {"male": ("Male", "Masculine, muscular or slim"),
                  "female": ("Female", "Feminine, curvy or slim"),
                  "trans": ("Trans/Futa", "Feminine with penis and breasts")}
AVATAR_RACES = {"white": "White/Caucasian", "black": "Black/African", "asian": "Asian",
                "hispanic": "Hispanic/Latino", "middle_eastern": "Middle Eastern",
                "indian": "Indian/South Asian"}
AVATAR_BUILDS = {"slim": "extremely skinny, petite, waif-like",
                 "athletic": "fit, toned, muscular",
                 "curvy": "full figured, wide hips",
                 "muscular": "ripped, bodybuilder"}
AVATAR_HAIR = {"blonde": "Blonde", "brunette": "Brunette", "black": "Black", "red": "Red",
               "pink": "Pink", "blue": "Blue", "purple": "Purple", "white": "White/Silver"}
AVATAR_SIZES = {"small": {"male": "small penis", "female": "small breasts", "trans": "small breasts and penis"},
                "medium": {"male": "medium penis", "female": "medium breasts", "trans": "medium breasts and penis"},
                "large": {"male": "large penis", "female": "large breasts", "trans": "large breasts and penis"}}

DOMINANT_POSES = [
    "three-quarter shot from the knees up, hands on hips, dominant stance",
    "three-quarter shot, arms crossed, looking down at camera, powerful",
    "three-quarter shot holding a riding crop across the chest, stern expression",
    "three-quarter shot seated on the edge of a chair, legs crossed, commanding",
    "three-quarter shot holding a leash, expectant expression",
    "three-quarter shot leaning against a doorframe, arms folded, chin lifted",
    "waist-up shot, finger pointing at camera, commanding gesture",
]
DOMINANT_OUTFITS_FEMALE = [
    "black latex catsuit", "leather corset and thigh-high boots", "sheer bodysuit with leather harness",
    "black PVC dress with choker", "fishnet bodysuit with straps", "leather harness over bare skin",
]
DOMINANT_OUTFITS_MALE = [
    "open black leather vest over bare chest, leather trousers",
    "bare-chested with a leather chest harness",
    "black latex trousers and a leather harness",
    "sleeveless black shirt, leather belt, leather trousers",
]
REWARD_POSES = [
    "kneeling upright, hands clasped behind back, chest pushed forward",
    "kneeling with thighs apart, hands flat on thighs, looking up at camera",
    "reclining on one elbow, hips turned toward camera, legs bent",
    "on all fours, back arched, looking over the shoulder at camera",
]
REWARD_GEAR = ["a black leather chest harness", "leather wrist cuffs and a collar",
               "a strappy leather body harness", "nothing but a leather collar"]
GENITAL_CLAUSE = {"male": "cock and balls clearly visible",
                  "female": "pussy clearly visible, breasts bare",
                  "trans": "cock and breasts clearly visible"}

GREETINGS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "hiya", "howdy"]
TASK_INQUIRIES = ["task", "my task", "current task", "what task", "do i have a task", "any task",
                  "status", "check task", "pending task"]
COMPLIMENTS = ["beautiful", "sexy", "hot", "gorgeous", "pretty", "cute", "amazing", "perfect", "love you"]
DISRESPECTFUL = ["fuck", "shit", "bitch", "stupid", "dumb", "hate", "suck", "idiot", "moron"]


def get_title(gender):
    return STUDIO_TITLE.get(gender or "", "Mistress")


def subject_clause(state):
    gender = state.get("avatar_gender") or state.get("gender") or "female"
    race = AVATAR_RACES.get(state.get("avatar_race") or "white", "White/Caucasian").split("/")[0]
    build = AVATAR_BUILDS.get(state.get("avatar_build") or "curvy", "full figured")
    hair = (state.get("avatar_hair") or "black").lower()
    size = AVATAR_SIZES.get(state.get("avatar_genital_size") or "medium", AVATAR_SIZES["medium"])
    return [f"Raw editorial photograph of a striking {race} {gender}", build, f"{hair} hair",
            size.get(gender, size["female"])]


def task_keyboard(task_id, title):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Done, {title}", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton("Not possible", callback_data=f"blocked_{task_id}")],
        [InlineKeyboardButton("I can't...", callback_data=f"giveup_{task_id}")],
        [InlineKeyboardButton("Mercy", callback_data=f"mercy_{task_id}")],
    ])


def risk_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{i}. {tk.RISK_LEVELS[i]['name']}",
                                                      callback_data=f"risk_{i}")]
                                 for i in range(1, 6)])


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
    levels = ["private", "semi", "exposed", "public"]
    return InlineKeyboardMarkup([[InlineKeyboardButton(("Y " if lv == selected else "") + lv,
                                                      callback_data=f"privacy_{lv}")] for lv in levels])


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
                       ("park", "Park"), ("bar", "Bar"), ("car", "Car"),
                       ("store", "Store"), ("work", "Work")]:
        row.append(InlineKeyboardButton(label, callback_data=f"venue_{key}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Somewhere else", callback_data="venue_custom")])
    return InlineKeyboardMarkup(rows)


def room_keyboard(venue_name, selected):
    rows = [[InlineKeyboardButton(("Y " if r in selected else "") + r.title(),
                                  callback_data=f"room_{i}")]
            for i, r in enumerate(venue.rooms_for_venue(venue_name))]
    rows.append([InlineKeyboardButton("Add a room", callback_data="room_custom"),
                 InlineKeyboardButton("That's the lot", callback_data="room_done")])
    return InlineKeyboardMarkup(rows)


def present_feature_keyboard(venue_name, rooms, selected):
    rows, row = [], []
    for ri, room in enumerate(rooms):
        for fi, feature in enumerate(venue.present_features(venue_name, room)):
            row.append(InlineKeyboardButton(("Y " if feature in selected else "") + feature[:18],
                                            callback_data=f"pf_{ri}_{fi}"))
            if len(row) == 2:
                rows.append(row)
                row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Add my own", callback_data="pf_custom"),
                 InlineKeyboardButton("Done", callback_data="pf_done")])
    return InlineKeyboardMarkup(rows)


def probe_keyboard(pool, selected):
    rows, row = [], []
    for i, item in enumerate(pool):
        row.append(InlineKeyboardButton(("Y " if item in selected else "") + item[:18],
                                        callback_data=f"probe_{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Add my own", callback_data="probe_custom"),
                 InlineKeyboardButton("Done", callback_data="probe_done")])
    return InlineKeyboardMarkup(rows)


def autopics_keyboard(on):
    return InlineKeyboardMarkup([[InlineKeyboardButton("Turn off" if on else "Turn on",
                                                      callback_data="autopics_toggle")]])


def _toggle(bucket, item):
    if item in bucket:
        bucket.remove(item)
    else:
        bucket.append(item)
    return bucket


async def generate_avatar(state, *, nude=False):
    gender = state.get("avatar_gender") or state.get("gender") or "female"
    spec = venice.get_spec(state.get("reward_model") if nude else None, nude=nude)

    async def build():
        if nude:
            return prompts.build(subject_clause(state), nude=True,
                                 gear=random.choice(REWARD_GEAR),
                                 pose=random.choice(REWARD_POSES),
                                 clause=GENITAL_CLAUSE.get(gender, "genitals clearly visible"))
        outfits = DOMINANT_OUTFITS_MALE if gender == "male" else DOMINANT_OUTFITS_FEMALE
        return prompts.build(subject_clause(state), nude=False,
                             pose=random.choice(DOMINANT_POSES),
                             outfit=random.choice(outfits))

    return await render.render_best(spec, build)


async def deliver_reward(bot, user_id, *, caption):
    state = st.get_state(user_id)
    png = await generate_avatar(state, nude=True)
    verdict = await verify.nude_check(png)
    if verdict == "COVERED":
        retry = await generate_avatar(state, nude=True)
        if await verify.nude_check(retry) != "COVERED":
            png = retry
    await storage.deliver(bot, user_id, user_id, png, caption=caption, prefix="reward")


async def autopics_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    on = bool(state.get("avatar_enabled"))
    await update.effective_message.reply_text(
        f"Scheduled photos: {'on' if on else 'off'}"
        f" (every {state.get('avatar_interval_minutes') or 60} min)",
        reply_markup=autopics_keyboard(on))


async def autopics_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    state["avatar_enabled"] = not bool(state.get("avatar_enabled"))
    if state["avatar_enabled"]:
        state["last_avatar_sent_at"] = None
    await q.edit_message_text(
        f"Scheduled photos: {'on' if state['avatar_enabled'] else 'off'}.",
        reply_markup=autopics_keyboard(state["avatar_enabled"]))


async def custom_input(update, context):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user or not msg.text:
        return
    state = st.get_state(user.id)
    pending = state.get("pending")
    if pending == "custom_location":
        state["venue"] = msg.text.strip()
        state["rooms"] = []
        state["features"] = {}
        state["pending"] = "custom_rooms"
        await msg.reply_text("Which rooms? Separate with commas.")
        return
    if pending == "custom_rooms":
        supplied = [p.strip() for p in msg.text.split(",") if p.strip()]
        if not supplied:
            await msg.reply_text("Nothing usable. Try again.")
            return
        state["pending"] = None
        if venue.rooms_for_venue(state.get("venue") or ""):
            state["rooms"] = (state.get("rooms") or []) + supplied
            await msg.reply_text("Added.", reply_markup=room_keyboard(state.get("venue") or "", state["rooms"]))
        else:
            state["rooms"] = supplied
            await msg.reply_text("Now the features inside those rooms.",
                                 reply_markup=present_feature_keyboard(state.get("venue") or "", supplied, []))
        return
    if pending == "custom_features":
        state["pending"] = None
        rooms = state.get("rooms") or []
        feats = state.setdefault("features", {})
        feats.setdefault(rooms[0] if rooms else "misc", []).append(msg.text.strip())
        chosen = [f for g in feats.values() for f in g]
        await msg.reply_text("Added.", reply_markup=present_feature_keyboard(
            state.get("venue") or "", rooms, chosen))
        return
    if pending == "custom_probe":
        pool = state.setdefault("probe_pool", [])
        state["pending"] = None
        if len(pool) < venue.MAX_PROBES:
            pool.append(msg.text.strip())
            state["probes"] = (state.get("probes") or []) + [msg.text.strip()]
        await msg.reply_text("Added.", reply_markup=probe_keyboard(pool, state.get("probes") or []))
        return
    if pending == "custom_outfit":
        state["current_outfit"] = "Custom: " + msg.text.strip()[:50]
        state["outfit_detail"] = msg.text.strip()[:300]
        state["outfit_items"] = [i.strip() for i in msg.text.split(",")][:6]
        state["pending"] = None
        await msg.reply_text("Noted. Use /wherenow.")
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

    session = st.get_session()
    try:
        has_task = bool(session.query(st.Task).filter_by(user_id=user.id, status="pending").first())
    finally:
        session.close()

    title = get_title(state.get("avatar_gender"))
    low = msg.text.lower()
    context_info = (f"User: {user.username or 'unknown'} | gender {state.get('gender')} | "
                    f"wearing {state.get('outfit_detail') or 'unknown'} | at "
                    f"{state.get('location') or 'unknown'} | points {state.get('points') or 0} | "
                    f"streak {state.get('streak') or 0} | task pending: {'yes' if has_task else 'no'}")

    if any(g in low for g in GREETINGS):
        ask = "They just greeted you. Tease them. 1-2 sentences."
    elif any(i in low for i in TASK_INQUIRIES):
        ask = ("They asked about their task. Tell them to stop stalling and finish it. 1-2 sentences."
               if has_task else "They asked for a task but have none. Tell them to use /task. 1-2 sentences.")
    elif any(c in low for c in COMPLIMENTS):
        ask = "They complimented you. Accept it as your due. 1-2 sentences."
    elif any(d in low for d in DISRESPECTFUL):
        ask = "They were disrespectful. Put them in their place. 1-2 sentences."
    else:
        ask = "Reply to them. Be playful, firm, 1-2 sentences. If lost, point at /task."

    await context.bot.send_chat_action(chat_id=msg.chat_id, action="typing")
    reply = await venice.chat(
        [{"role": "user", "content": f"{context_info}\n\nThey said: \"{msg.text}\"\n\n{ask}"}],
        DOM_VOICE, temperature=0.9)
    if not reply:
        reply = "Mmm? Something went wrong, pet. Try again."
    state["history"] = (state["history"] + [{"role": "assistant", "content": reply}])[-20:]
    await msg.reply_text(reply[:4000])


async def start_cmd(update, context):
    user = update.effective_user
    state = st.get_state(user.id)
    if not state.get("gender"):
        await update.effective_message.reply_text("Select gender:", reply_markup=gender_keyboard())
        return
    await update.effective_message.reply_text(
        f"Welcome back.\n\nLocation: {state.get('location') or 'Not set'}\n"
        f"Risk: {state.get('risk_level') or 5} | Points: {state.get('points') or 0} | "
        f"Streak: {state.get('streak') or 0}\n\n"
        f"/task /wherenow /outfit /avatar /risk /kinks /interval /schedule /status /rewards")


async def help_cmd(update, context):
    await update.effective_message.reply_text(
        "/task - get a challenge\n/wherenow - set location\n/outfit - set clothing\n"
        "/avatar - create avatar\n/reward - reward render\n/autopics - scheduled photos\n"
        "/risk - set risk\n/kinks - preferences\n/interval - auto interval\n"
        "/schedule - auto tasks on/off\n/status - check task\n/rewards - progress\n"
        "/clear - drop location\n/skip - skip detail\n/test - diagnostics\n/resetowner - wipe")


async def test_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text(
        f"pending: {state.get('pending')}\nlocation: {state.get('location') or 'unset'}\n"
        f"detail: {state.get('location_notes') or 'none'}\noutfit: {state.get('outfit_detail') or 'none'}\n"
        f"autopics: {state.get('avatar_enabled')}\n"
        f"model: {venice.IMAGE_MODEL} -> {venice.IMAGE_FALLBACKS}\n"
        f"upscale: {os.getenv('IMAGE_UPSCALE', '2')} sharpen: {os.getenv('IMAGE_SHARPEN', '1')}")


async def skip_cmd(update, context):
    st.get_state(update.effective_user.id)["pending"] = None
    await update.effective_message.reply_text("Fine. Use /task.")


async def gender_cmd(update, context):
    await update.effective_message.reply_text("Select gender:", reply_markup=gender_keyboard())


async def gender_callback(update, context):
    q = update.callback_query
    await q.answer()
    g = q.data.split("_", 1)[1]
    st.get_state(update.effective_user.id)["gender"] = g
    await q.edit_message_text(f"Gender: {g}. Use /outfit.")


async def outfit_cmd(update, context):
    await update.effective_message.reply_text("What are you wearing?", reply_markup=outfit_keyboard())


async def outfit_callback(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("_", 1)[1]
    state = st.get_state(update.effective_user.id)
    if key == "custom":
        state["pending"] = "custom_outfit"
        await q.edit_message_text("Describe your outfit.")
        return
    opt = tk.OUTFIT_OPTIONS[key]
    items = opt.get(f"{state.get('gender') or 'male'}_items", opt["male_items"])
    state["current_outfit"] = opt["name"]
    state["outfit_items"] = items
    state["pending"] = "outfit_detail"
    await q.edit_message_text(f"{opt['name']}, roughly.\n\nWhat are you actually in? Type it, or /skip.")


async def wherenow_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    state["venue"] = None
    state["rooms"] = []
    state["features"] = {}
    state["probes"] = []
    state["pending"] = None
    await update.effective_message.reply_text("Where are you?", reply_markup=venue_keyboard())


async def venue_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    if q.data == "venue_custom":
        state["pending"] = "custom_location"
        await q.edit_message_text("Describe exactly where you are.")
        return
    v = q.data.split("_", 1)[1]
    state["venue"] = v
    state["rooms"] = []
    state["features"] = {}
    if venue.rooms_for_venue(v):
        await q.edit_message_text("Which rooms?", reply_markup=room_keyboard(v, []))
    else:
        state["pending"] = "custom_rooms"
        await q.edit_message_text("List the rooms, comma separated.")


async def room_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    v = state.get("venue") or ""
    if q.data == "room_done":
        if not state.get("rooms"):
            await q.edit_message_text("Pick at least one room.")
            return
        await q.edit_message_text("Now the features.",
                                  reply_markup=present_feature_keyboard(v, state["rooms"], []))
        return
    if q.data == "room_custom":
        state["pending"] = "custom_rooms"
        await q.edit_message_text("Add a room name.")
        return
    rooms = venue.rooms_for_venue(v)
    i = int(q.data.split("_", 1)[1])
    if 0 <= i < len(rooms):
        _toggle(state.setdefault("rooms", []), rooms[i])
    await q.edit_message_reply_markup(reply_markup=room_keyboard(v, state["rooms"]))


async def present_feature_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    v = state.get("venue") or ""
    rooms = state.get("rooms") or []
    feats = state.setdefault("features", {})
    if q.data == "pf_done":
        await show_probes(q, update.effective_user.id, v, rooms,
                          [f for g in feats.values() for f in g])
        return
    if q.data == "pf_custom":
        state["pending"] = "custom_features"
        await q.edit_message_text("Describe the feature.")
        return
    _, ri, fi = q.data.split("_")
    ri, fi = int(ri), int(fi)
    if 0 <= ri < len(rooms):
        opts = venue.present_features(v, rooms[ri])
        if 0 <= fi < len(opts):
            _toggle(feats.setdefault(rooms[ri], []), opts[fi])
    await q.edit_message_reply_markup(reply_markup=present_feature_keyboard(
        v, rooms, [f for g in feats.values() for f in g]))


async def show_probes(q, user_id, v, rooms, chosen):
    state = st.get_state(user_id)
    baseline = venue.probe_options(v, rooms)
    known = [*rooms, *chosen, *baseline]
    await q.edit_message_text("Working out the details...")
    try:
        ai = await venice.generate_probes(v, rooms, known)
    except Exception:
        ai = []
    pool = (baseline + ai)[:venue.MAX_PROBES]
    state["probe_pool"] = pool
    state["probes"] = []
    await q.edit_message_text("Anything else worth pinning down?",
                              reply_markup=probe_keyboard(pool, []))


async def probe_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    pool = state.get("probe_pool") or []
    if q.data == "probe_done":
        await commit_location(q, update.effective_user.id)
        return
    if q.data == "probe_custom":
        state["pending"] = "custom_probe"
        await q.edit_message_text("Describe it.")
        return
    i = int(q.data.split("_", 1)[1])
    if 0 <= i < len(pool):
        _toggle(state.setdefault("probes", []), pool[i])
    await q.edit_message_reply_markup(reply_markup=probe_keyboard(pool, state["probes"]))


async def commit_location(q, user_id):
    state = st.get_state(user_id)
    v = state.get("venue") or ""
    rooms = state.get("rooms") or []
    feats = state.get("features") or {}
    probes = state.get("probes") or []
    lines = [f"Venue: {v}"]
    for room in rooms:
        picked = feats.get(room, [])
        lines.append(f"{room}: " + (", ".join(picked) if picked else "as is"))
    if probes:
        lines.append("Also: " + ", ".join(probes))
    notes = "\n".join(lines)
    state["location"] = v
    state["location_notes"] = notes
    state["pending"] = None
    await q.edit_message_text(f"{notes}\n\nWho is present?", reply_markup=present_keyboard())


async def present_callback(update, context):
    q = update.callback_query
    await q.answer()
    kind = q.data.split("_", 1)[1]
    state = st.get_state(update.effective_user.id)
    state["context_others"] = kind
    state["context_alone"] = (kind == "alone")
    if kind == "kids":
        cur = state.get("risk_level") or 5
        if cur > 2:
            state["risk_pre_kids"] = cur
            state["risk_level"] = 2
    elif state.get("risk_pre_kids"):
        state["risk_level"] = state["risk_pre_kids"]
        state["risk_pre_kids"] = None
    await q.edit_message_text("Privacy level?", reply_markup=privacy_keyboard(state.get("privacy")))


async def privacy_callback(update, context):
    q = update.callback_query
    await q.answer()
    state = st.get_state(update.effective_user.id)
    state["privacy"] = q.data.split("_", 1)[1]
    await q.edit_message_text(
        f"Locked in.\n\n{state.get('location_notes') or ''}\n\nUse /task.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Clear", callback_data="loc_clear")]]))


async def clear_location(update, context):
    state = st.get_state(update.effective_user.id)
    for k in ("location", "location_notes", "rooms", "probes", "venue", "features"):
        state[k] = None if k in ("location", "location_notes", "venue") else []
    state["pending"] = None
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Location cleared.")
    else:
        await update.effective_message.reply_text("Location cleared.")


async def risk_cmd(update, context):
    await update.effective_message.reply_text("Select risk:", reply_markup=risk_keyboard())


async def risk_callback(update, context):
    q = update.callback_query
    await q.answer()
    r = int(q.data.split("_", 1)[1])
    st.get_state(update.effective_user.id)["risk_level"] = r
    await q.edit_message_text(f"Risk: {tk.RISK_LEVELS[r]['name']}")


async def kinks_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    await update.effective_message.reply_text(
        "Kinks\n\nX = no\nO = okay\nY = desired\n\nTap to change:", reply_markup=kinks_keyboard(state))


async def kink_menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    key = q.data.split("_", 1)[1]
    state = st.get_state(update.effective_user.id)
    cur = state.get(key) or "okay"
    name, desc = tk.KINK_CATEGORIES[key]
    rows = [[InlineKeyboardButton(("Y " if cur == lv else "") + f"{tk.KINK_LEVELS[lv]['emoji']} {tk.KINK_LEVELS[lv]['name']}",
                                  callback_data=f"kinkset_{key}_{lv}")] for lv in ("no", "okay", "yes")]
    rows.append([InlineKeyboardButton("Back", callback_data="kinks_back")])
    await q.edit_message_text(f"{name}\n\n{desc}\n\nCurrent: {cur}", reply_markup=InlineKeyboardMarkup(rows))


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
    state = st.get_state(update.effective_user.id)
    await q.edit_message_text("Kinks\n\nTap to change:", reply_markup=kinks_keyboard(state))


async def kinks_done_callback(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Saved. Use /task.")


async def interval_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    state["pending"] = "interval"
    await update.effective_message.reply_text(
        f"Current: {state.get('min_interval')}-{state.get('max_interval')} minutes.\nSend as: MIN MAX")


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
        await q.edit_message_text("Auto tasks on.")
    else:
        state["scheduling_enabled"] = False
        state["next_task_time"] = None
        await q.edit_message_text("Auto tasks off.")


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
            await wherenow_cmd(update, context)
            return
        active = session.query(st.Task).filter_by(user_id=user.id, status="pending").first()
        if active:
            left = (active.expires_at - datetime.now(timezone.utc)).total_seconds() / 60
            await update.effective_message.reply_text(f"Pending! {max(0, left):.0f} minutes left.")
            return
        await update.effective_message.reply_text("Generating...")
        if random.random() < 0.3 and state.get("avatar_gender"):
            try:
                png = await generate_avatar(state)
                await storage.deliver(context.bot, user.id, user.id, png,
                                      caption="Your task awaits...", prefix="avatar")
            except Exception:
                logger.warning("pre-task avatar failed")
        text, risk = await tk.generate_task_text(state, session, voice=DOM_VOICE)
        now = datetime.now(timezone.utc)
        task = st.Task(user_id=user.id, task_text=text, risk_level=risk, created_at=now,
                       expires_at=now + timedelta(minutes=30))
        session.add(task)
        session.commit()
        context.job_queue.run_once(expire_task, when=timedelta(minutes=30),
                                   data={"user_id": user.id, "task_id": task.id})
        await update.effective_message.reply_text(
            f"{label}\n\n{text}\n\n30 minutes.",
            reply_markup=task_keyboard(task.id, get_title(state.get("avatar_gender"))))
    finally:
        session.close()


async def task_cmd(update, context):
    context.user_data.pop("blocked_task_id", None)
    await issue_task(update, context)


async def status_cmd(update, context):
    user = update.effective_user
    session = st.get_session()
    try:
        active = session.query(st.Task).filter_by(user_id=user.id, status="pending").first()
        if active:
            left = (active.expires_at - datetime.now(timezone.utc)).total_seconds() / 60
            await update.effective_message.reply_text(
                f"{max(0, left):.0f} min left\n\n{active.task_text[:200]}",
                reply_markup=task_keyboard(active.id, get_title(st.get_state(user.id).get("avatar_gender"))))
        else:
            await update.effective_message.reply_text("No active task. Use /task.")
    finally:
        session.close()


async def rewards_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    need = tk.reward_threshold(state.get("streak") or 0)
    await update.effective_message.reply_text(
        f"Rewards unlock every {need} completions.\n\nStreak: {state.get('streak') or 0}\n"
        f"Progress: {state.get('challenges_since_reward') or 0}/{need}\n\n/reward to trigger one now.")


async def complete_callback(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Send photo proof.")


async def blocked_callback(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["blocked_task_id"] = int(q.data.split("_", 1)[1])
    st.get_state(update.effective_user.id)["pending"] = "blocker"
    await q.edit_message_text("What's in the way?")


async def blocker_input(update, context):
    user = update.effective_user
    state = st.get_state(user.id)
    task_id = context.user_data.get("blocked_task_id")
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(id=task_id, user_id=user.id, status="pending").first()
        if not task:
            state["pending"] = None
            await update.effective_message.reply_text("That task is gone. Use /task.")
            return
        if task.blocked_count >= 3:
            await update.effective_message.reply_text("Three reworks. Use Mercy.")
            return
        state["pending"] = None
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
        await update.effective_message.reply_text("Reworking it.")
        new, risk = await tk.generate_task_text(state, session, voice=DOM_VOICE)
        task.task_text, task.risk_level = new, risk
        task.verification_attempts, task.followup_target = 0, None
        task.expires_at = now + timedelta(minutes=30)
        task.blocked_count += 1
        session.commit()
        await update.effective_message.reply_text(
            f"REWORKED\n\n{new}\n\n30 minutes.",
            reply_markup=task_keyboard(task.id, get_title(state.get("avatar_gender"))))
    finally:
        session.close()


async def mercy_callback(update, context):
    q = update.callback_query
    await q.answer()
    user = update.effective_user
    state = st.get_state(user.id)
    task_id = int(q.data.split("_", 1)[1])
    session = st.get_session()
    try:
        task = session.query(st.Task).filter_by(id=task_id, user_id=user.id, status="pending").first()
        if not task:
            await q.edit_message_text("No active task.")
            return
        await q.edit_message_text("Mercy granted. Finding something else...")
        new, risk = await tk.generate_task_text(state, session, voice=DOM_VOICE)
        now = datetime.now(timezone.utc)
        task.task_text, task.risk_level = new, risk
        task.verification_attempts, task.followup_target = 0, None
        task.expires_at = now + timedelta(minutes=30)
        session.commit()
        await context.bot.send_message(
            chat_id=user.id, text=f"NEW TASK\n\n{new}\n\n30 minutes.",
            reply_markup=task_keyboard(task.id, get_title(state.get("avatar_gender"))))
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
            state["points"] = max(0, (state.get("points") or 0) - 5)
            state["streak"] = 0
            session.commit()
            await q.edit_message_text("Abandoned. -5 points.")
    finally:
        session.close()


async def retry_callback(update, context):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Send retry photo.")


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
            await update.message.reply_text("Too small. Send a clearer one.")
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
            await update.message.reply_text("Expired. Use /task.")
            return
        verdict = await verify.verify_photo(data, task.task_text, task.followup_target)
        if verdict is None:
            await update.message.reply_text("Verifier unreachable - resend, no attempt used.")
            return
        verified, missing, reason = verdict
        task.verification_attempts += 1
        task.sharpness = int(await asyncio.to_thread(render.sharpness_score, data))
        if up:
            task.cloudinary_url, task.cloudinary_public_id = up["url"], up["public_id"]

        if verified == "yes":
            task.status, task.completed_at, task.photo_url = "completed", now, photo.file_id
            task.followup_target = None
            context.user_data.pop("blocked_task_id", None)
            state["points"] = (state.get("points") or 0) + 10 * task.risk_level
            state["streak"] = (state.get("streak") or 0) + 1
            state["completed_tasks"] = (state.get("completed_tasks") or 0) + 1
            state["challenges_since_reward"] = (state.get("challenges_since_reward") or 0) + 1
            session.commit()
            gain = 10 * task.risk_level
            need = tk.reward_threshold(state["streak"])
            if state["challenges_since_reward"] >= need:
                state["challenges_since_reward"] = 0
                await update.message.reply_text(f"+{gain} points. Streak {state['streak']}.\n\nReward earned.")
                try:
                    await deliver_reward(context.bot, user.id,
                                         caption=f"Yours, {get_title(state.get('avatar_gender'))}.")
                except Exception:
                    logger.exception("reward failed")
                    await update.message.reply_text("Reward render failed.")
            else:
                await update.message.reply_text(f"+{gain} points. Streak {state['streak']}.")
            return

        if task.verification_attempts >= 3:
            task.status = "failed"
            state["consecutive_failures"] = (state.get("consecutive_failures") or 0) + 1
            session.commit()
            await update.message.reply_text(f"Failed. {reason}")
            return
        task.followup_target = missing
        session.commit()
        left = 3 - task.verification_attempts
        body = (f"Not quite. I couldn't see {missing}. Show me {missing} - just that."
                if missing else f"Not quite. {reason} Once more.")
        await update.message.reply_text(
            f"{body}\n\n{left} {'try' if left == 1 else 'tries'} left.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Try Again", callback_data=f"retry_{task.id}"),
                InlineKeyboardButton("Give Up", callback_data=f"giveup_{task.id}")]]))
    except Exception:
        logger.exception("photo failed")
        await update.message.reply_text("Error processing that photo.")
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
        await context.bot.send_message(chat_id=user_id, text="Expired. -10 points.")
    except Exception:
        logger.exception("expire failed")
    finally:
        session.close()


async def avatar_cmd(update, context):
    state = st.get_state(update.effective_user.id)
    state["pending"] = "avatar_gender"
    await update.effective_message.reply_text(
        "Create avatar 1/5: gender",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(v[0], callback_data=f"av_gender_{k}")]
                                           for k, v in AVATAR_GENDERS.items()]))


async def avatar_gender_callback(update, context):
    q = update.callback_query
    await q.answer()
    g = q.data.split("_", 1)[1]
    context.user_data["av_gender"] = g
    await q.edit_message_text(f"Gender: {AVATAR_GENDERS[g][0]}\n\n2/5: race",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton(v, callback_data=f"av_race_{k}")]
                                   for k, v in AVATAR_RACES.items()]))


async def avatar_race_callback(update, context):
    q = update.callback_query
    await q.answer()
    r = q.data.split("_", 1)[1]
    context.user_data["av_race"] = r
    await q.edit_message_text(f"Race: {AVATAR_RACES[r]}\n\n3/5: build",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton(k, callback_data=f"av_build_{k}")]
                                   for k in AVATAR_BUILDS]))


async def avatar_build_callback(update, context):
    q = update.callback_query
    await q.answer()
    b = q.data.split("_", 1)[1]
    context.user_data["av_build"] = b
    await q.edit_message_text(f"Build: {b}\n\n4/5: hair",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton(v, callback_data=f"av_hair_{k}")]
                                   for k, v in AVATAR_HAIR.items()]))


async def avatar_hair_callback(update, context):
    q = update.callback_query
    await q.answer()
    h = q.data.split("_", 1)[1]
    context.user_data["av_hair"] = h
    await q.edit_message_text(f"Hair: {AVATAR_HAIR[h]}\n\n5/5: size",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton(k, callback_data=f"av_size_{k}")]
                                   for k in AVATAR_SIZES]))


async def avatar_size_callback(update, context):
    q = update.callback_query
    await q.answer()
    size = q.data.split("_", 1)[1]
    user = update.effective_user
    state = st.get_state(user.id)
    state["avatar_gender"] = context.user_data.get("av_gender")
    state["avatar_race"] = context.user_data.get("av_race")
    state["avatar_build"] = context.user_data.get("av_build")
    state["avatar_hair"] = context.user_data.get("av_hair")
    state["avatar_genital_size"] = size
    state["pending"] = None
    await q.edit_message_text("Generating...")
    try:
        png = await generate_avatar(state)
    except Exception:
        logger.exception("avatar failed")
        await q.edit_message_text("Render failed.")
        return
    up = await storage.upload_png(png, user.id, "avatar")
    session = st.get_session()
    try:
        session.add(st.AvatarImage(user_id=user.id, image_url="generated",
                                   cloudinary_url=up, gender=state.get("avatar_gender"),
                                   race=state.get("avatar_race"), build=state.get("avatar_build")))
        session.commit()
    finally:
        session.close()
    await storage.deliver(context.bot, user.id, user.id, png, caption="Your avatar.", prefix="avatar")


async def debugavatar_cmd(update, context):
    user = update.effective_user
    await update.effective_message.reply_text("Generating...")
    try:
        png = await generate_avatar(st.get_state(user.id))
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")
        return
    await render.debug_send(context.bot, png, label="avatar", chat_id=user.id, upscale_pass=True)


async def reward_cmd(update, context):
    user = update.effective_user
    await update.effective_message.reply_text("One sec...")
    try:
        await deliver_reward(context.bot, user.id, caption=f"Yours, {get_title(st.get_state(user.id).get('avatar_gender'))}.")
    except Exception as exc:
        await update.effective_message.reply_text(f"Failed: {exc}")


async def resetowner_cmd(update, context):
    await update.effective_message.reply_text(
        "Delete all data?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("YES", callback_data="reset_yes")],
            [InlineKeyboardButton("Cancel", callback_data="reset_no")]]))


async def reset_callback(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "reset_no":
        await q.edit_message_text("Cancelled.")
        return
    uid = update.effective_user.id
    session = st.get_session()
    try:
        for model in (st.LocationConstraint, st.Task, st.AvatarImage, st.UserImage, st.UserState):
            session.query(model).filter_by(user_id=uid).delete()
        session.commit()
        st.drop_state(uid)
        await q.edit_message_text("Deleted. Send /start.")
    finally:
        session.close()


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
            text, risk = await tk.generate_task_text(state, session, voice=DOM_VOICE)
            task = st.Task(user_id=row.user_id, task_text=text, risk_level=risk, created_at=now,
                           expires_at=now + timedelta(minutes=30))
            session.add(task)
            state["next_task_time"] = now + timedelta(
                minutes=random.randint(state.get("min_interval") or 30, state.get("max_interval") or 180))
            session.commit()
            context.job_queue.run_once(expire_task, when=timedelta(minutes=30),
                                       data={"user_id": row.user_id, "task_id": task.id})
            await context.bot.send_message(
                chat_id=row.user_id, text=f"AUTO TASK\n\n{text}\n\n30 minutes.",
                reply_markup=task_keyboard(task.id, get_title(state.get("avatar_gender"))))
            await asyncio.sleep(1)
        for row in session.query(st.UserState).filter(st.UserState.avatar_enabled == True).all():
            if not row.avatar_gender:
                continue
            last = row.last_avatar_sent_at
            if last and last + timedelta(minutes=row.avatar_interval_minutes or 60) > now:
                continue
            try:
                state = st.get_state(row.user_id)
                png = await generate_avatar(state)
                await storage.deliver(context.bot, row.user_id, row.user_id, png,
                                      caption=random.choice(["Thinking of you.", "Don't keep me waiting.",
                                                             "Ready to serve?"]), prefix="avatar")
                state["last_avatar_sent_at"] = now
            except Exception:
                logger.exception("periodic avatar failed")
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
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CommandHandler("skip", skip_cmd))
    app.add_handler(CommandHandler("gender", gender_cmd))
    app.add_handler(CommandHandler("outfit", outfit_cmd))
    app.add_handler(CommandHandler("wherenow", wherenow_cmd))
    app.add_handler(CommandHandler("clear", clear_location))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("kinks", kinks_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("interval", interval_cmd))
    app.add_handler(CommandHandler("avatar", avatar_cmd))
    app.add_handler(CommandHandler("reward", reward_cmd))
    app.add_handler(CommandHandler("autopics", autopics_cmd))
    app.add_handler(CommandHandler("debugavatar", debugavatar_cmd))
    app.add_handler(CommandHandler("resetowner", resetowner_cmd))
    app.add_handler(CommandHandler("rewards", rewards_cmd))

    app.add_handler(CallbackQueryHandler(gender_callback, pattern="^gender_"))
    app.add_handler(CallbackQueryHandler(outfit_callback, pattern="^outfit_"))
    app.add_handler(CallbackQueryHandler(venue_callback, pattern="^venue_"))
    app.add_handler(CallbackQueryHandler(room_callback, pattern="^room_"))
    app.add_handler(CallbackQueryHandler(present_feature_callback, pattern="^pf_"))
    app.add_handler(CallbackQueryHandler(probe_callback, pattern="^probe_"))
    app.add_handler(CallbackQueryHandler(clear_location, pattern="^loc_clear$"))
    app.add_handler(CallbackQueryHandler(present_callback, pattern="^present_"))
    app.add_handler(CallbackQueryHandler(privacy_callback, pattern="^privacy_"))
    app.add_handler(CallbackQueryHandler(risk_callback, pattern="^risk_"))
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
    app.add_handler(CallbackQueryHandler(autopics_callback, pattern="^autopics_toggle$"))
    app.add_handler(CallbackQueryHandler(reset_callback, pattern="^reset_"))
    app.add_handler(CallbackQueryHandler(avatar_gender_callback, pattern="^av_gender_"))
    app.add_handler(CallbackQueryHandler(avatar_race_callback, pattern="^av_race_"))
    app.add_handler(CallbackQueryHandler(avatar_build_callback, pattern="^av_build_"))
    app.add_handler(CallbackQueryHandler(avatar_hair_callback, pattern="^av_hair_"))
    app.add_handler(CallbackQueryHandler(avatar_size_callback, pattern="^av_size_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_input))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(error_handler)

    app.job_queue.run_repeating(scheduled_check, interval=60, first=10,
                                job_kwargs={"misfire_grace_time": 180, "coalesce": True, "max_instances": 1})
    logger.info("dombot up")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()