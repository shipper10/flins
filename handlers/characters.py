from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from utils.mongo import users_collection, logs_collection
from utils.escape import escape_text
from datetime import datetime
from genshin import GenshinClient

async def characters(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        chars = await client.get_characters(int(user_data["UID"]))
        msg = "*🗡 شخصياتك:*\n"
        for c in chars:
            msg += f"- {escape_text(c.name)} Lv.{escape_text(c.level)} | C{escape_text(c.constellation)} | {escape_text(c.weapon.name)}\n"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logs_collection.insert_one({
            "user_id": user_id,
            "error": str(e),
            "time": datetime.utcnow(),
            "context": "/characters"
        })
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات الشخصيات.")

def characters_handler():
    from telegram.ext import CommandHandler
    return CommandHandler("characters", characters)
