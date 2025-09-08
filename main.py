import os
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from genshin import GenshinClient, AlreadyClaimed
from genshin.models import DiaryType
from pymongo import MongoClient

# ---------------- Environment Variables ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# ---------------- MongoDB ----------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.genshin_bot
users_collection = db.users
logs_collection = db.logs

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Helpers ----------------
def get_client(user_data):
    return GenshinClient(
        ltuid_v2=user_data.get("ltuid_v2"),
        ltoken_v2=user_data.get("ltoken_v2"),
        ltmid_v2=user_data.get("ltmid_v2"),
        cookie_token_v2=user_data.get("cookie_token_v2")
    )

# ---------------- Registration ----------------
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 تسجيل المستخدم:\n"
        "يمكنك التسجيل عن طريق:\n"
        "1️⃣ إدخال الكوكيز كاملة.\n"
        "2️⃣ تسجيل الدخول بالبريد وكلمة السر.\n\n"
        "اكتب 'cookies' أو 'login' للمتابعة."
    )

async def handle_register_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text == "cookies":
        await update.message.reply_text(
            "📌 أدخل الكوكيز بالترتيب:\n"
            "ltuid_v2, ltoken_v2, ltmid_v2, cookie_token_v2\n"
            "افصل بين كل قيمة بفاصلة."
        )
        context.user_data["reg_method"] = "cookies"
    elif text == "login":
        await update.message.reply_text("📌 أدخل البريد الإلكتروني:")
        context.user_data["reg_method"] = "login"
        context.user_data["step"] = "email"
    else:
        await update.message.reply_text("❌ الرجاء كتابة 'cookies' أو 'login'.")

async def handle_register_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    method = context.user_data.get("reg_method")
    text = update.message.text.strip()
    try:
        if method == "cookies":
            parts = [p.strip() for p in text.split(",")]
            if len(parts) != 4:
                await update.message.reply_text("❌ الرجاء إدخال جميع القيم الأربع للكوكيز.")
                return
            ltuid_v2, ltoken_v2, ltmid_v2, cookie_token_v2 = parts
            client = GenshinClient(ltuid_v2=ltuid_v2, ltoken_v2=ltoken_v2, ltmid_v2=ltmid_v2, cookie_token_v2=cookie_token_v2)
        elif method == "login":
            step = context.user_data.get("step")
            if step == "email":
                context.user_data["email"] = text
                context.user_data["step"] = "password"
                await update.message.reply_text("📌 أدخل كلمة المرور:")
                return
            elif step == "password":
                email = context.user_data.get("email")
                password = text
                client = GenshinClient(email=email, password=password)
        else:
            await update.message.reply_text("❌ خطأ في طريقة التسجيل.")
            return

        user_info = await client.get_partial_genshin_user(client.user_id)
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "UID": str(client.user_id),
                "ltuid_v2": getattr(client, "ltuid_v2", ""),
                "ltoken_v2": getattr(client, "ltoken_v2", ""),
                "ltmid_v2": getattr(client, "ltmid_v2", ""),
                "cookie_token_v2": getattr(client, "cookie_token_v2", "")
            }},
            upsert=True
        )
        await update.message.reply_text(f"✅ تم التسجيل بنجاح! UID: `{client.user_id}`", parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"خطأ أثناء التسجيل للمستخدم {user_id}: {e}")
        await update.message.reply_text(f"❌ حدث خطأ أثناء التسجيل: {e}")

# ---------------- /profile ----------------
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = get_client(user_data)
        user = await client.get_partial_genshin_user(int(user_data["UID"]))
        msg = (
            f"*👤 بيانات المستخدم:*\n"
            f"- Adventure Rank: `{user.stats.adventure_rank}`\n"
            f"- عدد الشخصيات: `{len(user.characters)}`\n"
        )
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"خطأ في /profile للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "/profile"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات الملف الشخصي.")

# ---------------- /characters ----------------
async def characters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = get_client(user_data)
        chars = await client.get_characters(int(user_data["UID"]))
        msg = "*🗡 شخصياتك:*\n"
        for c in chars:
            msg += f"- {c.name} Lv.{c.level} | C{c.constellation} | {c.weapon.name}\n"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"خطأ في /characters للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "/characters"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات الشخصيات.")

# ---------------- /abyss ----------------
async def abyss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = get_client(user_data)
        current = await client.get_spiral_abyss(int(user_data["UID"]))
        prev = await client.get_spiral_abyss(int(user_data["UID"]), previous=True)
        msg = (
            f"*🌀 Spiral Abyss الحالي:*\n"
            f"- Stars: `{current.total_stars}`\n"
            f"- Floors: `{len(current.floors)}`\n\n"
            f"*↩ Spiral Abyss السابق:*\n"
            f"- Stars: `{prev.total_stars}`\n"
            f"- Floors: `{len(prev.floors)}`\n"
        )
        keyboard = [
            [InlineKeyboardButton("⬅ السابق", callback_data="abyss_previous")],
            [InlineKeyboardButton("➡ الحالي", callback_data="abyss_current")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطأ في /abyss للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "/abyss"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات Spiral Abyss.")

# ---------------- /resin ----------------
async def resin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = get_client(user_data)
        notes = await client.get_daily_notes(int(user_data["UID"]))
        msg = f"*🛡 Resin الحالي:* `{notes.resin}` | الوقت المتبقي: `{notes.resin_recovery_time}`"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"خطأ في /resin للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "/resin"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات Resin.")

# ---------------- /resources_diary ----------------
async def resources_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = get_client(user_data)
        notes = await client.get_daily_notes(int(user_data["UID"]))
        msg = (
            f"💎 *Primogems الحالية:* `{notes.primogems}`\n"
            f"💰 *Mora الحالية:* `{notes.mora}`\n"
            f"\nاختر المورد لعرض إحصائياته التاريخية:"
        )
        keyboard = [
            [InlineKeyboardButton("💎 Primogems", callback_data="resource_primogems")],
            [InlineKeyboardButton("💰 Mora", callback_data="resource_mora")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطأ في resources_diary للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "resources_diary"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب بيانات الموارد.")

async def resources_diary_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    try:
        client = get_client(user_data)
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
            msg += f"💎 *Primogems المكتسبة ({period}):* `{diary.data.current_primogems}`\n\n"
            msg += "*🔹 مصادر Primogems:*\n"
            for cat in diary.data.categories:
                msg += f"- {cat.percentage}% من {cat.name} (`{cat.amount}` primogems)\n"
        elif resource == "mora":
            msg += f"💰 *سجل Mora ({period}):*\n"
            async for action in client.diary_log(limit=50, type=DiaryType.MORA):
                msg += f"- {action.action} : `{action.amount}` mora\n"
        await query.edit_message_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"خطأ في resources_diary_button للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "resources_diary_button"})
        await query.edit_message_text("❌ حدث خطأ أثناء جلب بيانات الموارد التاريخية.")

# ---------------- /daily_rewards ----------------
async def daily_rewards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        await update.message.reply_text("❌ أنت غير مسجل. استخدم /register أولاً في الخاص.")
        return
    try:
        client = get_client(user_data)
        signed_in, claimed_count = await client.get_reward_info()
        status = "✅ تم تسجيل الدخول اليومي" if signed_in else "❌ لم يتم تسجيل الدخول اليوم"
        msg = f"*📊 حالة المكافأة اليومية:*\n{status}\n*عدد المكافآت المطالبة:* `{claimed_count}`"
        keyboard = [
            [InlineKeyboardButton("🎁 المطالبة بالمكافأة اليومية", callback_data="claim_daily")],
            [InlineKeyboardButton("📜 عرض المكافآت المطالبة", callback_data="view_claimed")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"خطأ في daily_rewards للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "daily_rewards"})
        await update.message.reply_text("❌ حدث خطأ أثناء جلب حالة المكافآت اليومية.")

async def daily_rewards_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = users_collection.find_one({"user_id": user_id})
    try:
        client = get_client(user_data)
        if query.data == "claim_daily":
            try:
                reward = await client.claim_daily_reward()
                msg = f"✅ تم المطالبة بالمكافأة اليومية: {reward.amount}x {reward.name}"
            except AlreadyClaimed:
                msg = "⚠️ تم المطالبة بالمكافأة اليومية بالفعل اليوم."
            await query.edit_message_text(msg)
        elif query.data == "view_claimed":
            msg = "*📜 المكافآت المطالبة سابقًا:*\n"
            async for reward in client.claimed_rewards():
                msg += f"- {reward.time} : {reward.amount}x {reward.name}\n"
            await query.edit_message_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"خطأ في daily_rewards_button للمستخدم {user_id}: {e}")
        logs_collection.insert_one({"user_id": user_id, "error": str(e), "time": datetime.utcnow(), "context": "daily_rewards_button"})
        await query.edit_message_text("❌ حدث خطأ أثناء تنفيذ العملية.")

# ---------------- Handlers ----------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Registration
app.add_handler(CommandHandler("register", register))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_register_input))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_register_details))

# Commands
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("characters", characters))
app.add_handler(CommandHandler("abyss", abyss))
app.add_handler(CommandHandler("resin", resin))
app.add_handler(CommandHandler("resources_diary", resources_diary))
app.add_handler(CallbackQueryHandler(resources_diary_button, pattern="^resource_(primogems|mora)(_week|_month|_3months)?$"))
app.add_handler(CommandHandler("daily_rewards", daily_rewards))
app.add_handler(CallbackQueryHandler(daily_rewards_button, pattern="^(claim_daily|view_claimed)$"))

# ---------------- Run Bot ----------------
app.run_polling()
