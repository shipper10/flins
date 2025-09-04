# bot.py
# Telegram bot that integrates genshin.py (Battle Chronicle) and Enka (showcase + optional image cards)
# Requirements:
# pip install python-telegram-bot==20.7 genshin aiosqlite enka-py Pillow python-dotenv
# Optional: pip install enkacard enkanetworkcard

import os
import io
import logging
import asyncio
from typing import Optional, Tuple

import aiosqlite
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import genshin

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
# Database helpers
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
            "INSERT INTO users (tg_id, uid) VALUES (?, ?) ON CONFLICT(tg_id) DO UPDATE SET uid=excluded.uid",
            (tg_id, uid),
        )
        await db.commit()

async def set_cookies(tg_id: int, ltuid_v2: str, ltoken_v2: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (tg_id, ltuid_v2, ltoken_v2) VALUES (?, ?, ?) ON CONFLICT(tg_id) DO UPDATE SET ltuid_v2=excluded.ltuid_v2, ltoken_v2=excluded.ltoken_v2",
            (tg_id, ltuid_v2, ltoken_v2),
        )
        await db.commit()

async def get_user_row(tg_id: int) -> Optional[Tuple[int, Optional[int], Optional[str], Optional[str]]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tg_id, uid, ltuid_v2, ltoken_v2 FROM users WHERE tg_id=?", (tg_id,)) as cur:
            row = await cur.fetchone()
            return row

# ----------------------------
# Utility helpers
# ----------------------------

def require_token() -> str:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is missing. Put it in .env or environment.")
    return TELEGRAM_TOKEN

async def get_client_for_user(tg_id: int) -> genshin.Client:
    row = await get_user_row(tg_id)
    cookies = {}
    if row:
        _, _, ltuid_v2, ltoken_v2 = row
        if ltuid_v2 and ltoken_v2:
            cookies = {"ltuid_v2": ltuid_v2, "ltoken_v2": ltoken_v2}
    client = genshin.Client(cookies) if cookies else genshin.Client()
    return client

async def ensure_uid(update: Update) -> Optional[int]:
    row = await get_user_row(update.effective_user.id)
    if row and row[1]:
        return int(row[1])
    await update.effective_message.reply_text("⚠️ لم تضبط UID بعد. استخدم /setuid 800123456.")
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
# Command handlers
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
👋 أهلاً! هذا بوت Genshin يدعم:
• genshin.py لعرض Daily Note / Abyss / Diary
• Enka لعرض Showcase وبطاقات صور (إن توفرت مكتبة التوليد)

الأوامر:
/setuid <UID> — ضبط UID
/setcookies <ltuid_v2> <ltoken_v2> — ربط الكوكيز
/daily — Resin والملاحظات اليومية
/abyss [prev] — عرض Abyss الحالي أو السابق
/diary — Primogem/Mora diary
/showcase — جلب Showcase من Enka
/card [uid] — توليد بطاقة صورة
        """.strip()
    )

# --- الأوامر الأخرى مثل setuid_cmd, setcookies_cmd, daily_cmd, abyss_cmd, diary_cmd, showcase_cmd, card_cmd ---
# انسخ نفس التعريفات الموجودة لديك بدون تغيير

# ----------------------------
# Main
# ----------------------------

def main():
    require_token()
    
    # تهيئة DB قبل التشغيل
    asyncio.get_event_loop().run_until_complete(init_db())

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setuid", setuid_cmd))
    app.add_handler(CommandHandler("setcookies", setcookies_cmd))
    app.add_handler(CommandHandler("daily", daily_cmd))
    app.add_handler(CommandHandler("abyss", abyss_cmd))
    app.add_handler(CommandHandler("diary", diary_cmd))
    app.add_handler(CommandHandler("showcase", showcase_cmd))
    app.add_handler(CommandHandler("card", card_cmd))

    # Simple help alias
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await start(update, context)
    app.add_handler(CommandHandler("help", help_cmd))

    logger.info("Bot started")
    # تشغيل البوت بدون asyncio.run()
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
