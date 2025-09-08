from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from utils.mongo import users_collection, logs_collection
from utils.escape import escape_text
from datetime import datetime
from genshin import GenshinClient

async def abyss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = GenshinClient(
            ltuid_v2=user_data.get("ltuid_v2"),
            ltoken_v2=user_data.get("ltoken_v2"),
            ltmid_v2=user_data.get("ltmid_v2"),
            cookie_token_v2=user_data.get("cookie_token_v2")
        )
        current = await client.get_spiral_abyss(int(user_data["UID"]))
        prev = await client.get_spiral_abyss(int(user_data["UID"]), previous=True)
        msg = (
            f"*🌀 Spiral Abyss الحالي:*\n"
            f"- Stars: `{escape_text(current.total_stars)}`\n"
            f"- Floors: `{escape_text(len(current.floors))}`\n\n"
            f"*↩ Spiral Abyss السابق:*\n"
            f"- Stars: `{escape_text(prev.total_stars)}`\n"
            f"- Floors: `{escape_text(len(prev.floors))}`\n"
        )
        keyboard = [
            [InlineKeyboardButton("⬅ السابق", callback_data="abyss_previous")],
            [InlineKeyboardButton("➡ الحالي", callback_data="abyss_current")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except Exception as e:
        logs_collection.insert_one({
            "user_id": user_id,
            "error": str(e),
            "time": datetime.utcnow(),
            "context": "/abyss"
        })
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات Spiral Abyss.")

def abyss_handler():
    from telegram.ext import CommandHandler
    return CommandHandler("abyss", abyss)
