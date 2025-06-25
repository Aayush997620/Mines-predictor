import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, ConversationHandler
)
from PIL import Image, ImageDraw
import hashlib
import random
import io
import os
import json
from datetime import datetime

# --- Configuration ---
BOT_TOKEN = os.environ.get("8096540176:AAG5XKMIZLZhnubCD1WwOZHIV6EpZf1lv2M")  # Use environment variable for security
PASSKEY_BASIC = "AjdJe62BHkaie"
PASSKEY_PREMIUM = "Sushru73TyaMisGHn"

# --- Plan Configuration ---
PLAN_CONFIG = {
    "basic": {"days": 15, "daily_limit": 15},
    "premium": {"days": 31, "daily_limit": 45}
}

# --- Conversation States ---
ASK_PLAN, ASK_PASS, ASK_CLIENT_SEED = range(3)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- User Data File ---
USER_DATA_FILE = "user_data.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f)

# --- /start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.first_name
    user_db = load_user_data()

    if user_id in user_db and user_db[user_id].get("expired", False):
        await update.message.reply_text("⛔ Your plan has expired. Contact admin to reactivate.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("1️⃣ Stake Mines", callback_data="basic")],
        [InlineKeyboardButton("💎 Stake Mines Premium", callback_data="premium")]
    ]
    await update.message.reply_text(
        f"👋 Hello *{username}*!\n\n"
        "📢 *Disclaimer:*\n"
        "You have two plan options:\n\n"
        "1️⃣ *Stake Mines* - Valid for 15 days.\n"
        "   ➤ Get 15 sure-shot signals daily for 15 days.\n\n"
        "💎 *Stake Mines Premium* - Valid for 31 days.\n"
        "   ➤ Get 45 sure-shot signals daily for 31 days.\n\n"
        "🔔 *Recommendation:* It is better to choose the Premium plan for maximum benefit.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_PLAN

# --- Plan Selected ---
async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan = query.data
    context.user_data["plan"] = plan
    await query.edit_message_text(f"✅ You selected the *{plan.capitalize()}* plan.\n\n🔐 Please enter your access *passkey*:", parse_mode="Markdown")
    return ASK_PASS

# --- Passkey Validation ---
async def check_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_pass = update.message.text.strip()
    plan = context.user_data["plan"]
    user_db = load_user_data()

    if (plan == "basic" and user_pass == PASSKEY_BASIC) or (plan == "premium" and user_pass == PASSKEY_PREMIUM):
        today = datetime.utcnow().date().isoformat()
        user_db[user_id] = {
            "plan": plan,
            "start_date": today,
            "last_used_date": today,
            "signals_used_today": 0,
            "expired": False
        }
        save_user_data(user_db)

        await update.message.reply_text(
            "✅ Passkey verified!\n⚠️ You must play only with *3 mines*.\n\nNow enter your *Client Seed*:",
            parse_mode="Markdown"
        )
        return ASK_CLIENT_SEED
    else:
        await update.message.reply_text("❌ Incorrect passkey. Try again.")
        return ASK_PASS

# --- Handle Client Seed ---
async def handle_client_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_db = load_user_data()
    today = datetime.utcnow().date()

    if user_id not in user_db:
        await update.message.reply_text("⚠️ Please start again using /start.")
        return ConversationHandler.END

    user_info = user_db[user_id]
    plan = user_info["plan"]
    config = PLAN_CONFIG[plan]
    start_date = datetime.fromisoformat(user_info["start_date"]).date()

    # Expiry check
    if (today - start_date).days > config["days"]:
        user_info["expired"] = True
        save_user_data(user_db)
        await update.message.reply_text("❌ Your plan has expired. Contact admin to reactivate.")
        return ConversationHandler.END

    # Daily reset
    if user_info["last_used_date"] != today.isoformat():
        user_info["last_used_date"] = today.isoformat()
        user_info["signals_used_today"] = 0

    # Signal limit check
    if user_info["signals_used_today"] >= config["daily_limit"]:
        await update.message.reply_text("⚠️ You've reached today's signal limit. Please come back after 12:00 AM.")
        save_user_data(user_db)
        return ASK_CLIENT_SEED

    # Proceed with prediction
    seed = update.message.text.strip()
    user_info["signals_used_today"] += 1
    save_user_data(user_db)

    safe_tiles = generate_safe_tiles(seed, 3)
    image = generate_prediction_image(safe_tiles)

    await update.message.reply_photo(photo=image, caption=f"✅ Prediction for seed: `{seed}`", parse_mode="Markdown")
    keyboard = [[InlineKeyboardButton("📦 Next Signal", callback_data="next_signal")]]
    await update.message.reply_text("Ready for next signal?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_CLIENT_SEED

# --- Next Signal Button ---
async def next_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔢 Please enter your *next Client Seed*:", parse_mode="Markdown")
    return ASK_CLIENT_SEED

# --- /status Command ---
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_db = load_user_data()

    if user_id not in user_db:
        await update.message.reply_text("⚠️ You haven't selected any plan yet. Use /start to begin.")
        return

    user_info = user_db[user_id]
    plan = user_info["plan"]
    config = PLAN_CONFIG[plan]
    start_date = datetime.fromisoformat(user_info["start_date"]).date()
    today = datetime.utcnow().date()

    used = user_info.get("signals_used_today", 0)
    remaining = config["daily_limit"] - used
    days_used = (today - start_date).days
    days_total = config["days"]
    days_left = max(0, days_total - days_used)

    if user_info.get("expired", False) or days_left <= 0:
        await update.message.reply_text("❌ Your plan has expired. Contact admin to reactivate.")
        return

    await update.message.reply_text(
        f"📊 *Your Plan Status:*\n\n"
        f"🔹 *Plan:* {plan.capitalize()}\n"
        f"📅 *Days Left:* {days_left} / {days_total}\n"
        f"📈 *Signals Today:* {used} / {config['daily_limit']}\n",
        parse_mode="Markdown"
    )

# --- Fallback Handler ---
async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚠️ Invalid input. Please follow the instructions or use /start to begin again.")

# --- Generate Safe Tiles ---
def generate_safe_tiles(seed: str, num_mines: int):
    hashed = hashlib.sha256(seed.encode()).hexdigest()
    random.seed(int(hashed, 16))
    tiles = list(range(25))
    random.shuffle(tiles)
    return sorted(tiles[:5])

# --- Generate Prediction Image ---
def generate_prediction_image(safe_tiles):
    tile_size = 64
    grid_size = 5
    img = Image.new("RGB", (tile_size * grid_size, tile_size * grid_size), color=(20, 20, 30))
    draw = ImageDraw.Draw(img)

    for index in range(25):
        row, col = divmod(index, 5)
        x, y = col * tile_size, row * tile_size
        draw.rectangle([x+4, y+4, x+tile_size-4, y+tile_size-4], fill=(40, 45, 60))
        if index in safe_tiles:
            draw.polygon([(x+32, y+10), (x+50, y+32), (x+32, y+54), (x+14, y+32)], fill=(0, 255, 140))
            draw.line([(x+32, y+10), (x+32, y+54)], fill=(0, 190, 100), width=2)
            draw.line([(x+14, y+32), (x+50, y+32)], fill=(0, 190, 100), width=2)

    output = io.BytesIO()
    img.save(output, format='PNG')
    output.seek(0)
    return output

# --- Main Function ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_PLAN: [CallbackQueryHandler(plan_selected)],
            ASK_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_pass)],
            ASK_CLIENT_SEED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_seed),
                CallbackQueryHandler(next_signal, pattern="^next_signal$")
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback_handler)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("status", status))  # Add status command
    logger.info("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
