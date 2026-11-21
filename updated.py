import os
import random
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

# ==========================================
# 1. CONFIG
# ==========================================
BOT_TOKEN = "8645466073:AAGho0HHg9yPwMpKNDtG-5GW1uH5NwMfAYo"
OWNER_ID = 9071386675
CHANNEL_USERNAME = "@nafaelmain1"
CHANNEL_LINK = "https://t.me/nafaelmain1"

BRAND_NAME = "nafael"
DB_PATH = "bot_users.db"

DATABASE_FILE = "database.txt"
USED_FILE = "usednames.txt"
RESULTS_DIR = "results"
UPASS_OUTPUT_BASE = os.path.join(RESULTS_DIR, "nafael_upass")

WAIT_COUNTRY, WAIT_AMOUNT, WAIT_RANGE = range(3)
ACTIVE_SESSIONS = {}

COUNTRIES = {
    "PH": ("🇵🇭", "Philippines"),
    "ID": ("🇮🇩", "Indonesia"),
    "US": ("🇺🇸", "United States"),
    "MY": ("🇲🇾", "Malaysia"),
    "SG": ("🇸🇬", "Singapore"),
    "GLOBAL": ("🌍", "Mixed/Global"),
}

# ==========================================
# 2. DATABASE
# ==========================================
import sqlite3
import time

def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                uid INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                banned INTEGER DEFAULT 0,
                joined_at INTEGER,
                last_gen INTEGER DEFAULT 0,
                daily_gens INTEGER DEFAULT 0,
                last_reset DATE,
                referred_by INTEGER,
                bonus_gens INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0
            )
        """)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def register_user(uid, username, first_name, referred_by=None):
    today = datetime.now().date()
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
        if not row:
            conn.execute("""
                INSERT INTO users (uid, username, first_name, joined_at, last_reset, referred_by) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uid, username or "", first_name or "", int(time.time()), today, referred_by))
            if referred_by:
                conn.execute("UPDATE users SET referral_count = referral_count + 1, bonus_gens = bonus_gens + 1 WHERE uid=?", (referred_by,))
        else:
            conn.execute("UPDATE users SET username=?, first_name=? WHERE uid=?", (username or "", first_name or "", uid))

def check_daily_reset(uid):
    today = datetime.now().date()
    with db() as conn:
        row = conn.execute("SELECT daily_gens, last_reset FROM users WHERE uid=?", (uid,)).fetchone()
        if row and str(row["last_reset"]) != str(today):
            conn.execute("UPDATE users SET daily_gens = 0, last_reset = ? WHERE uid=?", (today, uid))

def get_user_stats(uid):
    check_daily_reset(uid)
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()

def update_gen_stats(uid):
    with db() as conn:
        conn.execute("UPDATE users SET last_gen = ?, daily_gens = daily_gens + 1 WHERE uid=?", (int(time.time()), uid))

def use_bonus_gen(uid):
    with db() as conn:
        conn.execute("UPDATE users SET bonus_gens = bonus_gens - 1 WHERE uid=?", (uid,))

def use_credit(uid):
    with db() as conn:
        conn.execute("UPDATE users SET credits = credits - 1 WHERE uid=? AND credits > 0", (uid,))

def is_banned(uid):
    with db() as conn:
        row = conn.execute("SELECT banned FROM users WHERE uid=?", (uid,)).fetchone()
        return bool(row and row["banned"])

# ==========================================
# 3. GEN1 LOGIC
# ==========================================
def load_used():
    if not os.path.exists(USED_FILE):
        return set()
    with open(USED_FILE, "r", encoding="utf-8") as file:
        return {line.strip() for line in file if line.strip()}

def save_used(usernames):
    if not usernames: return
    with open(USED_FILE, "a", encoding="utf-8") as file:
        for username in usernames:
            file.write(username + "\n")

def load_file(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]

def get_numbered_filename(base_path):
    directory = os.path.dirname(base_path)
    filename = os.path.basename(base_path)
    root, ext = os.path.splitext(filename)
    os.makedirs(directory, exist_ok=True)
    number = 1
    while True:
        candidate = os.path.join(directory, f"{root} ({number}){ext}")
        if not os.path.exists(candidate):
            return candidate
        number += 1

def generate_upass(amount, start_num, end_num, session_id):
    database = load_file(DATABASE_FILE)
    if not database:
        return None, "database.txt is empty or missing."

    used = load_used()
    database = list(dict.fromkeys(database))
    random.shuffle(database)
    generated = []

    suffixes = [""]
    if start_num is not None and end_num is not None:
        suffixes = [f"{i:02d}" if i < 100 else str(i) for i in range(start_num, end_num + 1)]

    for raw_line in database:
        if len(generated) >= amount: break
        if ACTIVE_SESSIONS.get(session_id, {}).get("cancelled"):
            return None, "Cancelled"

        name = raw_line.split(",", 1)[0].strip()
        if not name or " " in name or not name.isalpha(): continue
        if not (4 <= len(name) <= 15): continue

        name = name[0].upper() + name[1:]
        numbers = suffixes.copy()
        random.shuffle(numbers)
        username = None

        for suffix in numbers:
            candidate = f"{name}{suffix}"
            if candidate in used: continue
            username = candidate
            break

        if username is None: continue

        generated.append(f"{username}:{username}")
        used.add(username)

    return generated, "Success"

def save_upass(generated):
    if not generated: return None
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_file = get_numbered_filename(UPASS_OUTPUT_BASE + ".txt")
    with open(output_file, "w", encoding="utf-8") as file:
        file.write("\n".join(generated))
        file.write("\n")
    usernames = [line.split(":", 1)[0] for line in generated]
    save_used(usernames)
    return output_file

# ==========================================
# 4. UI
# ==========================================
def get_main_menu(uid):
    kb = [
        [InlineKeyboardButton("⚡ Generate Combos", callback_data="menu_gen")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="menu_refer")],
        [InlineKeyboardButton("📝 Send Feedback", callback_data="menu_fb")],
    ]
    if uid == OWNER_ID:
        kb.append([InlineKeyboardButton("👑 Admin Panel", callback_data="menu_admin")])
    return InlineKeyboardMarkup(kb)

def get_admin_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="menu_home")]])

def get_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_join")]
    ])

def get_country_keyboard():
    kb = []
    items = list(COUNTRIES.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(f"{items[i][1][0]} {items[i][1][1]}", callback_data=f"c_{items[i][0]}")]
        if i + 1 < len(items):
            row.append(InlineKeyboardButton(f"{items[i+1][1][0]} {items[i+1][1][1]}", callback_data=f"c_{items[i+1][0]}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("↩ Cancel", callback_data="menu_home")])
    return InlineKeyboardMarkup(kb)

def format_time(seconds):
    mins, secs = divmod(seconds, 60)
    return f"{int(mins)}m {int(secs)}s"

# ==========================================
# 5. HANDLERS
# ==========================================
async def check_joined(user_id, bot):
    if user_id == OWNER_ID: return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError:
        return False

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    referred_by = None
    if ctx.args and len(ctx.args) > 0:
        try:
            ref_id = int(ctx.args[0])
            if ref_id != uid: referred_by = ref_id
        except ValueError: pass
            
    register_user(uid, update.effective_user.username, update.effective_user.first_name, referred_by)
    
    if is_banned(uid):
        await update.message.reply_text("🚫 <b>Access Denied.</b>\nYou have been banned.", parse_mode="HTML")
        return ConversationHandler.END
        
    if not await check_joined(uid, ctx.bot):
        await update.message.reply_text(
            f"⚠️ <b>Access Denied</b>\n\nJoin our channel to use this bot.",
            reply_markup=get_join_keyboard(), parse_mode="HTML"
        )
        return ConversationHandler.END

    role = "Owner" if uid == OWNER_ID else "User"
    await update.message.reply_text(
        f"👋 <b>Welcome, {update.effective_user.first_name}!</b>\n"
        f"Your Role: <code>{role}</code>\n\nSelect an option below:",
        reply_markup=get_main_menu(uid), parse_mode="HTML"
    )
    return ConversationHandler.END

async def give_credits(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    args = ctx.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /give <user_id> <amount>")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid ID or amount.")
        return
        
    with db() as conn:
        row = conn.execute("SELECT uid FROM users WHERE uid=?", (target_id,)).fetchone()
        if not row:
            await update.message.reply_text("❌ User not found in database.")
            return
        conn.execute("UPDATE users SET credits = credits + ? WHERE uid=?", (amount, target_id))
        
    await update.message.reply_text(f"✅ <b>Credits Added to</b> <code>{target_id}</code>: +{amount}", parse_mode="HTML")

async def menu_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = update.effective_user.id

    if data == "menu_home":
        role = "Owner" if uid == OWNER_ID else "User"
        await query.edit_message_text(
            f"👋 <b>Welcome, {update.effective_user.first_name}!</b>\nYour Role: <code>{role}</code>\n\nSelect an option:",
            reply_markup=get_main_menu(uid), parse_mode="HTML"
        )
    elif data == "menu_admin" and uid == OWNER_ID:
        await query.edit_message_text("👑 <b>Admin Panel</b>", reply_markup=get_admin_menu(), parse_mode="HTML")
    elif data == "menu_refer":
        bot_info = await ctx.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={uid}"
        stats = get_user_stats(uid)
        text = (
            f"🔗 <b>Refer & Earn</b>\n\n"
            f"Invite friends to get 1 Free Generation!\n\n"
            f"<b>Your Stats:</b>\n"
            f"👥 Friends Invited: <code>{stats['referral_count']}</code>\n"
            f"🎁 Bonus Generations: <code>{stats['bonus_gens']}</code>\n"
            f"💰 Credits: <code>{stats['credits']}</code>\n\n"
            f"<b>Your Link:</b>\n<code>{ref_link}</code>"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="menu_home")]]), parse_mode="HTML")
    elif data == "menu_gen":
        if is_banned(uid):
            await query.edit_message_text("🚫 You are banned.", parse_mode="HTML")
            return ConversationHandler.END
            
        if uid != OWNER_ID:
            stats = get_user_stats(uid)
            if stats["credits"] > 0:
                await query.edit_message_text("🌍 <b>Step 1/2: Select Country</b>\n<i>(Using 1 Credit)</i>", reply_markup=get_country_keyboard(), parse_mode="HTML")
                return WAIT_COUNTRY

            now = int(time.time())
            time_passed = now - stats["last_gen"]
            if time_passed < 300:
                remaining = 300 - time_passed
                await query.edit_message_text(f"⏳ <b>Cooldown Active</b>\n\nWait <b>{format_time(remaining)}</b>.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Refer a Friend", callback_data="menu_refer")]]), parse_mode="HTML")
                return ConversationHandler.END
                
            if stats["daily_gens"] >= 3 and stats["bonus_gens"] <= 0:
                await query.edit_message_text(f"🚫 <b>Daily Limit Reached</b>\n\nYou have used 3 free generations today.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Refer a Friend", callback_data="menu_refer")]]), parse_mode="HTML")
                return ConversationHandler.END

        await query.edit_message_text("🌍 <b>Step 1/2: Select Country</b>", reply_markup=get_country_keyboard(), parse_mode="HTML")
        return WAIT_COUNTRY

async def verify_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if await check_joined(uid, ctx.bot):
        await query.message.edit_text(f"✅ <b>Verified!</b>\nSelect an option:", reply_markup=get_main_menu(uid), parse_mode="HTML")
    else:
        await query.message.edit_text(f"❌ <b>Verification Failed</b>\nYou haven't joined yet.", reply_markup=get_join_keyboard(), parse_mode="HTML")

async def feedback_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await check_joined(update.effective_user.id, ctx.bot):
        await query.edit_message_text("❌ Please verify you joined the channel first.", reply_markup=get_join_keyboard())
        return ConversationHandler.END
    await query.edit_message_text("📝 <b>Send Feedback</b>\n\nType your message now.\nType /cancel to abort.", parse_mode="HTML")
    return WAIT_FEEDBACK

async def feedback_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin_header = f"📩 <b>NEW FEEDBACK</b>\n\n👤 {user.first_name}\n🔗 @{user.username or 'None'}\n🆔 <code>{user.id}</code>"
    try:
        await ctx.bot.send_message(chat_id=OWNER_ID, text=admin_header, parse_mode="HTML")
        if update.message.photo:
            await ctx.bot.send_photo(chat_id=OWNER_ID, photo=update.message.photo[-1].file_id, caption=update.message.caption)
        elif update.message.document:
            await ctx.bot.send_document(chat_id=OWNER_ID, document=update.message.document.file_id, caption=update.message.caption)
        else:
            await ctx.bot.send_message(chat_id=OWNER_ID, text=update.message.text)
        await update.message.reply_text("✅ <b>Feedback Sent!</b>", reply_markup=get_main_menu(user.id), parse_mode="HTML")
    except Exception:
        await update.message.reply_text("❌ Failed to send.", reply_markup=get_main_menu(user.id))
    return ConversationHandler.END

async def country_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    code = query.data.split("_")[1]
    flag, name = COUNTRIES[code]
    ctx.user_data["country"] = f"{flag} {name}"
    limit = "5,000,000" if update.effective_user.id == OWNER_ID else "10,000"
    await query.edit_message_text(
        f"🌍 <b>Country:</b> {flag} {name}\n\n🔢 <b>Step 2/3: Amount</b>\nSend how many combos to generate (Max: {limit}).",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Cancel", callback_data="menu_home")]])
    )
    return WAIT_AMOUNT

async def amount_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_joined(uid, ctx.bot):
        await update.message.reply_text("❌ You left the channel.", reply_markup=get_join_keyboard())
        return ConversationHandler.END

    try:
        amount = int(update.message.text.strip())
        if amount <= 0: raise ValueError
        if uid != OWNER_ID and amount > 10000:
            await update.message.reply_text("❌ <b>Limit Exceeded</b>\nMax 10,000 lines.", parse_mode="HTML")
            return WAIT_AMOUNT
        elif uid == OWNER_ID and amount > 5000000:
            amount = 5000000
    except ValueError:
        await update.message.reply_text("❌ Please send a valid number.")
        return WAIT_AMOUNT

    ctx.user_data["amount"] = amount
    await update.message.reply_text("🔢 <b>Step 3/3: Number Range</b>\n\nSend a range like <code>25-80</code>.\nOr tap /skip to generate without numbers.", parse_mode="HTML")
    return WAIT_RANGE

async def skip_range(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["range"] = (None, None)
    return await start_generation(update, ctx)

async def range_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["skip", "/skip", "none"]:
        ctx.user_data["range"] = (None, None)
        return await start_generation(update, ctx)

    try:
        start_text, end_text = text.split("-", 1)
        start_num = int(start_text.strip())
        end_num = int(end_text.strip())
        if start_num < 0 or end_num < start_num or end_num > 999:
            raise ValueError
        ctx.user_data["range"] = (start_num, end_num)
    except ValueError:
        await update.message.reply_text("❌ Invalid range. Use format like <code>25-80</code> or type /skip.", parse_mode="HTML")
        return WAIT_RANGE

    return await start_generation(update, ctx)

async def start_generation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    amount = ctx.user_data.get("amount")
    start_num, end_num = ctx.user_data.get("range", (None, None))
    country = ctx.user_data.get("country", "Global")
    
    if uid != OWNER_ID:
        stats = get_user_stats(uid)
        if stats["credits"] > 0: use_credit(uid)
        elif stats["bonus_gens"] > 0: use_bonus_gen(uid)
        update_gen_stats(uid)
    
    if update.message:
        msg = await update.message.reply_text("⏳ <b>Processing...</b>\nPlease wait.", parse_mode="HTML")
    else:
        msg = await ctx.bot.send_message(chat_id=uid, text="⏳ <b>Processing...</b>\nPlease wait.", parse_mode="HTML")

    session_id = f"{uid}_{int(datetime.now().timestamp())}"
    ACTIVE_SESSIONS[session_id] = {"cancelled": False}
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Cancel", callback_data=f"cancel_{session_id}")]])

    admin_msg = await ctx.bot.send_message(
        chat_id=OWNER_ID,
        text=f"🔔 <b>Live Session</b>\n\n👤 User: {user.first_name}\n🆔 ID: <code>{user.id}</code>\n📦 Target: {amount:,}\n\n📊 <b>Status:</b> Running...",
        reply_markup=cancel_kb, parse_mode="HTML"
    )

    loop = asyncio.get_event_loop()
    generated, result = await loop.run_in_executor(None, lambda: generate_upass(amount, start_num, end_num, session_id))
    ACTIVE_SESSIONS.pop(session_id, None)

    if result == "Cancelled":
        await msg.edit_text("🛑 <b>Cancelled.</b>", parse_mode="HTML")
        await admin_msg.edit_text("🛑 <b>Cancelled.</b>", reply_markup=None, parse_mode="HTML")
    elif not generated:
     