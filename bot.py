# bot.py
# Telegram bot for Genshin Impact (genshin.py + Enka)
# Requirements:
#   pip install python-telegram-bot==20.7 genshin aiosqlite enka-py Pillow python-dotenv
# Optional (image cards):
#   pip install enkacard enkanetworkcard

import os
import io
import asyncio
import logging
from typing import Optional, Tuple

import aiosqlite
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

import genshin  # genshin.py

# Enka
try:
    from enkapy import EnkaAPI
except Exception:
    EnkaAPI = None

# Optional image card generators
try:
    import enkacard
except Exception:
    enkacard = None

try:
    from enkanetworkcard import encbanner
except Exception:
    encbanner = None

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genshin_telegram_bot")

DB_PATH = os.getenv("DB_PATH", "genshin_bot.db")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# ----------------------------
# Database
# ----------------------------
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS users (
  tg_id INTEGER PRIMARY KEY,
  uid INTEGER,
  ltuid_v2 TEXT,
  ltoken_v2 TEXT
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_SQL)
        await db.commit()

async def set_uid(tg_id: int, uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (tg_id, uid) VALUES (?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET uid=excluded.uid",
            (tg_id, uid),
        )
        await db.commit()

async def set_cookies(tg_id: int, ltuid_v2: str, ltoken_v2: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (tg_id, ltuid_v2, ltoken_v2) VALUES (?, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET ltuid_v2=excluded.ltuid_v2, ltoken_v2=excluded.ltoken_v2",
            (tg_id, ltuid_v2, ltoken_v2),
        )
        await db.commit()

async def get_user_row(tg_id: int) -> Optional[Tuple[int, Optional[int], Optional[str], Optional[str]]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tg_id, uid, ltuid_v2, ltoken_v2 FROM users WHERE tg_id=?", (tg_id,)) as cur:
            return await cur.fetchone()

# ----------------------------
# Utils
# ----------------------------
def require_token() -> str:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is missing in .env")
    return TELEGRAM_TOKEN

async def get_client_for_user(tg_id: int) -> genshin.Client:
    row = await get_user_row(tg_id)
    cookies = {}
    if row:
        _, _, ltuid_v2, ltoken_v2 = row
        if ltuid_v2 and ltoken_v2:
            cookies = {"ltuid_v2": ltuid_v2, "ltoken_v2": ltoken_v2}
    return genshin.Client(cookies) if cookies else genshin.Client()

async def ensure_uid(update: Update) -> Optional[int]:
    row = await get_user_row(update.effective_user.id)
    if row and row[1]:
        return int(row[1])
    await update.effective_message.reply_text("⚠️ UID غير مضبوط. استخدم /setuid 800123456")
    return None

async def render_fallback_card_text(uid: int, title: str, lines: list[str]) -> bytes:
    W, H = 900, 600
    img = Image.new("RGB", (W, H), color=(22, 24, 28))
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("arial.ttf", 40)
        font_text = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
    draw.text((30, 25), f"Genshin – UID {uid}", fill=(255, 255, 255), font=font_title)
    y = 90
    draw.text((30, y), title, fill=(200, 220, 255), font=font_text)
    y += 40
    for line in lines:
        draw.text((30, y), line, fill=(235, 235, 235), font=font_text)
        y += 34
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

# ----------------------------
# Commands
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! هذا بوت Genshin:\n"
        "/setuid <UID>\n"
        "/setcookies <ltuid_v2> <ltoken_v2>\n"
        "/daily\n"
        "/abyss [prev]\n"
        "/diary\n"
        "/showcase\n"
        "/card [uid]"
    )

async def setuid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استخدم: /setuid 800123456")
        return
    try:
        uid = int(context.args[0])
        await set_uid(update.effective_user.id, uid)
        await update.message.reply_text(f"✅ تم ضبط UID: {uid}")
    except ValueError:
        await update.message.reply_text("UID غير صالح.")

async def setcookies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استخدم: /setcookies <ltuid_v2> <ltoken_v2>")
        return
    ltuid_v2, ltoken_v2 = context.args[0], context.args[1]
    await set_cookies(update.effective_user.id, ltuid_v2, ltoken_v2)
    await update.message.reply_text("✅ تم ربط الكوكيز (v2)")

# --- Daily, Abyss, Diary, Showcase commands تبقى كما هي من نسخة سابقة ---
# على سبيل الاختصار، أتركها كما هي. يمكن إضافتها بدون تغييرات في handlers.

# ----------------------------
# Main
# ----------------------------
def main():
    require_token()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setuid", setuid_cmd))
    app.add_handler(CommandHandler("setcookies", setcookies_cmd))
    # أضف باقي handlers هنا مثل daily_cmd, abyss_cmd, diary_cmd, showcase_cmd, card_cmd

    # تشغيل البوت
    app.run_polling()

if __name__ == "__main__":
    main()
