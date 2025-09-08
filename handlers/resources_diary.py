from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from utils.mongo import users_collection, logs_collection
from utils.escape import escape_text
from datetime import datetime
from genshin import GenshinClient, DiaryType

async def resources_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        notes = await client.get_daily_notes(int(user_data["UID"]))
        msg = (
            f"💎 *Primogems الحالية:* `{escape_text(notes.primogems)}`\n"
            f"💰 *Mora الحالية:* `{escape_text(notes.mora)}`\n\n"
            "اختر المورد لعرض إحصائياته التاريخية:"
        )
        keyboard = [
            [InlineKeyboardButton("💎 Primogems", callback_data="resource_primogems")],
            [InlineKeyboardButton("💰 Mora", callback_data="resource_mora")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except Exception as e:
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "resources_diary"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات الموارد.")

async def resources_diary_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    try:
        client = GenshinClient(
            ltuid_v2=user_data.get("ltuid_v2"),
            ltoken_v2=user_data.get("ltoken_v2"),
            ltmid_v2=user_data.get("ltmid_v2"),
            cookie_token_v2=user_data.get("cookie_token_v2")
        )

        if query.data in ["resource_primogems", "resource_mora"]:
            keyboard = [
                [InlineKeyboardButton("🗓 آخر أسبوع", callback_data=f"{query.data}_week")],
                [InlineKeyboardButton("📅 آخر شهر", callback_data=f"{query.data}_month")],
                [InlineKeyboardButton("📆 آخر 3 أشهر", callback_data=f"{query.data}_3months")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("اختر الفترة الزمنية:", reply_markup=reply_markup)
            return

        data_parts = query.data.split("_")
        resource = data_parts[1]
        period = data_parts[2]
        msg = ""

        if resource == "primogems":
            diary = await client.get_diary()
            msg += f"💎 *Primogems المكتسبة ({escape_text(period)}):* `{escape_text(diary.data.current_primogems)}`\n\n"
            msg += "*🔹 مصادر Primogems:*\n"
            for cat in diary.data.categories:
                msg += f"- {escape_text(cat.percentage)}% من {escape_text(cat.name)} (`{escape_text(cat.amount)}` primogems)\n"
        elif resource == "mora":
            msg += f"💰 *سجل Mora ({escape_text(period)}):*\n"
            async for action in client.diary_log(limit=50, type=DiaryType.MORA):
                msg += f"- {escape_text(action.action)} : `{escape_text(action.amount)}` mora\n"

        await query.edit_message_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "resources_diary_button"})
        await query.edit_message_text("❌ حدث خطأ أثناء جلب بيانات الموارد التاريخية.")

def resources_diary_handler():
    from telegram.ext import CommandHandler, CallbackQueryHandler
    handlers = [
        CommandHandler("resources_diary", resources_diary),
        CallbackQueryHandler(resources_diary_button, pattern="^resource_(primogems|mora)(_week|_month|_3months)?$")
    ]
    return handlers
