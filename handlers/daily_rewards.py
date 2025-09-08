from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from utils.mongo import users_collection, logs_collection
from utils.escape import escape_text
from datetime import datetime
from genshin import GenshinClient, AlreadyClaimed

async def daily_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        signed_in, claimed_count = await client.get_reward_info()
        status = "✅ تم تسجيل الدخول اليومي" if signed_in else "❌ لم يتم تسجيل الدخول اليوم"
        msg = f"*📊 حالة المكافأة اليومية:*\n{escape_text(status)}\n*عدد المكافآت المطالبة:* `{escape_text(claimed_count)}`"
        keyboard = [
            [InlineKeyboardButton("🎁 المطالبة بالمكافأة اليومية", callback_data="claim_daily")],
            [InlineKeyboardButton("📜 عرض المكافآت المطالبة", callback_data="view_claimed")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except Exception as e:
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "daily_rewards"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب حالة المكافآت اليومية.")

async def daily_rewards_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        if query.data == "claim_daily":
            try:
                reward = await client.claim_daily_reward()
                msg = f"✅ تم المطالبة بالمكافأة اليومية: {escape_text(reward.amount)}x {escape_text(reward.name)}"
            except AlreadyClaimed:
                msg = "⚠️ تم المطالبة بالمكافأة اليومية بالفعل اليوم."
            await query.edit_message_text(msg)
        elif query.data == "view_claimed":
            msg = "*📜 المكافآت المطالبة سابقًا:*\n"
            async for reward in client.claimed_rewards():
                msg += f"- {escape_text(reward.time)} : {escape_text(reward.amount)}x {escape_text(reward.name)}\n"
            await query.edit_message_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "daily_rewards_button"})
        await query.edit_message_text("❌ حدث خطأ أثناء تنفيذ العملية.")

def daily_rewards_handler():
    from telegram.ext import CommandHandler, CallbackQueryHandler
    handlers = [
        CommandHandler("daily_rewards", daily_rewards),
        CallbackQueryHandler(daily_rewards_button, pattern="^(claim_daily|view_claimed)$")
    ]
    return handlers
