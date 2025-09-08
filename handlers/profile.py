from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from utils.mongo import users_collection, logs_collection
from utils.escape import escape_text
from datetime import datetime
from genshin import GenshinClient

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        user = await client.get_partial_genshin_user(int(user_data["UID"]))
        msg = (
            f"*👤 بيانات المستخدم:*\n"
            f"- Adventure Rank: `{escape_text(user.stats.adventure_rank)}`\n"
            f"- عدد الشخصيات: `{escape_text(len(user.characters))}`\n"
        )
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logs_collection.insert_one({
            "user_id": user_id,
            "error": str(e),
            "time": datetime.utcnow(),
            "context": "/profile"
        })
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات الملف الشخصي.")

def profile_handler():
    from telegram.ext import CommandHandler
    return CommandHandler("profile", profile)
