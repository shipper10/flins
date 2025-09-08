from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from genshin import GenshinClient
from utils.mongo import users_collection, logs_collection
from utils.escape import escape_text
from datetime import datetime

CHOOSING_METHOD, ENTERING_DETAILS = range(2)

async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 تسجيل المستخدم:\nاختر الطريقة:\n1️⃣ cookies\n2️⃣ login"
    )
    return CHOOSING_METHOD

async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text not in ["cookies", "login"]:
        await update.message.reply_text("❌ الرجاء كتابة 'cookies' أو 'login'.")
        return CHOOSING_METHOD
    context.user_data["reg_method"] = text
    if text == "cookies":
        await update.message.reply_text("📌 أدخل الكوكيز بالترتيب: ltuid_v2, ltoken_v2, ltmid_v2, cookie_token_v2")
    else:
        await update.message.reply_text("📌 أدخل البريد الإلكتروني:")
        context.user_data["step"] = "email"
    return ENTERING_DETAILS

async def enter_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # هنا ضع الكود لمعالجة الكوكيز أو البريد/كلمة السر
    await update.message.reply_text("✅ تم التسجيل بنجاح!")
    return ConversationHandler.END

def register_handler():
    from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters
    return ConversationHandler(
        entry_points=[CommandHandler("register", start_register)],
        states={
            CHOOSING_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_method)],
            ENTERING_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_details)]
        },
        fallbacks=[]
    )
