# bot.py
# Telegram bot that integrates genshin.py (Battle Chronicle) and Enka (showcase + optional image cards)
# Requirements (install):
#   pip install python-telegram-bot==20.7 genshin aiosqlite enka-py Pillow python-dotenv
# Optional (for image cards):
#   pip install enkacard enkanetworkcard
#
# Usage:
#   1) Create a .env file with TELEGRAM_TOKEN=123:ABC...
#   2) python bot.py
#
# Notes:
#  - Users must set their UID and cookies (/setuid, /setcookies) before calling /daily, /abyss, /diary.
#  - We use ltuid_v2 / ltoken_v2 cookies. If you only have ltuid/ltoken, try logging out/in and copy the _v2 ones.

import os
import io
import asyncio
import logging
from typing import Optional, Tuple

import aiosqlite
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from telegram import Update, InputFile
from telegram.constants import ParseMode
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import genshin  # genshin.py

# Enka data client
try:
    from enkapy import EnkaAPI  # enka-py
except Exception:
    EnkaAPI = None

# Optional image card generators
try:
    # Preferred, newer template-based generator
    import enkacard  # type: ignore
except Exception:
    enkacard = None

try:
    # Simpler banner/card generator
    from enkanetworkcard import encbanner  # type: ignore
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
        await db.execute("INSERT INTO users (tg_id, uid) VALUES (?, ?) ON CONFLICT(tg_id) DO UPDATE SET uid=excluded.uid", (tg_id, uid))
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

# Fallback image if no card generator available
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
/setcookies <ltuid_v2> <ltoken_v2> — ربط الكوكيز (لازم لعرض البيانات الخاصة)
/daily — Resin والملاحظات اليومية
/abyss [prev] — عرض Abyss الحالي (أو السابق إذا كتبت prev)
/diary — Primogem/Mora diary
/showcase — جلب Showcase من Enka
/card [uid] — توليد بطاقة صورة (إذا متوفر مولد)
        """.strip()
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

async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await ensure_uid(update)
    if uid is None:
        return
    client = await get_client_for_user(update.effective_user.id)
    try:
        notes = await client.get_genshin_notes(uid=uid)
        text = (
            f"📝 Daily Note\n"
            f"Resin: {notes.current_resin}/{notes.max_resin}\n"
            f"Expeditions: {notes.current_expeditions}/{notes.max_expeditions}\n"
            f"Realm Currency: {notes.current_realm_currency}/{notes.max_realm_currency}"
        )
        await update.message.reply_text(text)
    except genshin.errors.InvalidCookies:
        await update.message.reply_text("❌ كوكيز غير صالحة. استخدم /setcookies ltuid_v2 ltoken_v2")
    except Exception as e:
        logger.exception("daily error")
        await update.message.reply_text(f"❌ خطأ: {e}")

async def abyss_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await ensure_uid(update)
    if uid is None:
        return
    client = await get_client_for_user(update.effective_user.id)
    previous = False
    if context.args and context.args[0].lower() in {"prev", "previous", "old"}:
        previous = True
    try:
        abyss = await client.get_genshin_spiral_abyss(uid=uid, previous=previous)
        lines = [
            f"🌀 Spiral Abyss ({'previous' if previous else 'current'})",
            f"Max Floor: {getattr(abyss, 'max_floor', 'N/A')}",
            f"Total Stars: {getattr(abyss, 'total_stars', 'N/A')}",
        ]
        # Print a small summary of floors if available
        floors = getattr(abyss, 'floors', []) or []
        for f in floors[:4]:
            f_index = getattr(f, 'floor', getattr(f, 'index', '?'))
            f_stars = getattr(f, 'total_stars', getattr(f, 'stars', '?'))
            lines.append(f"Floor {f_index}: ⭐ {f_stars}")
        # Try to render a quick image card if generators exist
        img_bytes = await render_fallback_card_text(uid, lines[0], lines[1:])
        await update.message.reply_photo(photo=img_bytes, caption="\n".join(lines[:5]))
    except genshin.errors.InvalidCookies:
        await update.message.reply_text("❌ كوكيز غير صالحة. استخدم /setcookies ltuid_v2 ltoken_v2")
    except Exception as e:
        logger.exception("abyss error")
        await update.message.reply_text(f"❌ خطأ: {e}")

async def diary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await ensure_uid(update)
    if uid is None:
        return
    client = await get_client_for_user(update.effective_user.id)
    try:
        diary = await client.get_genshin_diary(uid=uid)
        # Newer versions return model with .data sometimes
        data = getattr(diary, 'data', diary)
        total = getattr(data, 'current_primogems', getattr(data, 'primogems', 'N/A'))
        mora = getattr(data, 'current_mora', getattr(data, 'mora', 'N/A'))
        lines = [f"💎 Primogems: {total}", f"🪙 Mora: {mora}"]
        await update.message.reply_text("\n".join(lines))
    except genshin.errors.Deprecated as e:
        await update.message.reply_text(f"⚠️ تنبيه: {e}")
    except genshin.errors.InvalidCookies:
        await update.message.reply_text("❌ كوكيز غير صالحة. استخدم /setcookies ltuid_v2 ltoken_v2")
    except Exception as e:
        logger.exception("diary error")
        await update.message.reply_text(f"❌ خطأ: {e}")

async def showcase_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = await ensure_uid(update)
    if uid is None:
        return
    if EnkaAPI is None:
        await update.message.reply_text("❌ تحتاج لتثبيت enka-py: pip install enka-py")
        return
    try:
        api = EnkaAPI()
        user = await api.fetch_user(uid)
        chars = getattr(user, 'characters', [])
        if not chars:
            await update.message.reply_text("لا توجد شخصيات في الـ Showcase أو الحساب خاص.")
            return
        lines = [f"👤 Showcase ({len(chars)} شخصيات):"]
        for c in chars[:10]:
            name = getattr(c, 'name', 'Unknown')
            level = getattr(c, 'level', '?')
            wpn_name = getattr(getattr(c, 'weapon', None), 'name', '—')
            lines.append(f"• {name} Lv.{level} – {wpn_name}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.exception("showcase error")
        await update.message.reply_text(f"❌ خطأ: {e}")

async def card_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /card [uid]
    # Prefer enkacard; fallback to enkanetworkcard; else fallback image
    uid_arg = None
    if context.args:
        try:
            uid_arg = int(context.args[0])
        except Exception:
            uid_arg = None
    uid = uid_arg or await ensure_uid(update)
    if uid is None:
        return

    # Try enkacard first
    if enkacard is not None:
        try:
            # The enkacard API may vary by version; we attempt a generic entrypoint
            # Many builds expose: from enkacard import Card; await Card(uid).render()
            # We'll try a safe pathway; if it fails, fall back.
            if hasattr(enkacard, "Card"):
                Card = getattr(enkacard, "Card")
                card = Card(uid=uid)  # type: ignore
                # Some versions are async, others sync. Try both.
                if hasattr(card, "render"):
                    res = card.render()  # may return PIL.Image or bytes/path
                    if asyncio.iscoroutine(res):
                        res = await res
                    # Normalize to bytes
                    if isinstance(res, Image.Image):
                        buf = io.BytesIO()
                        res.save(buf, format="PNG")
                        buf.seek(0)
                        img_bytes = buf.read()
                    elif isinstance(res, (bytes, bytearray)):
                        img_bytes = bytes(res)
                    elif isinstance(res, str) and os.path.exists(res):
                        with open(res, "rb") as f:
                            img_bytes = f.read()
                    else:
                        raise RuntimeError("Unsupported enkacard render output")
                    await update.message.reply_photo(photo=img_bytes, caption=f"Enka Card – UID {uid}")
                    return
        except Exception as e:
            logger.warning(f"enkacard failed: {e}")

    # Fallback to enkanetworkcard banner
    if encbanner is not None:
        try:
            ENC = encbanner.EnkaGenshinGeneration(lang="en", hide=True)
            # This call usually generates a file path; adapt if it returns PIL.Image or bytes
            path_or_obj = ENC.start(uids=uid, template=2)
            if isinstance(path_or_obj, Image.Image):
                buf = io.BytesIO()
                path_or_obj.save(buf, format="PNG")
                buf.seek(0)
                img_bytes = buf.read()
            elif isinstance(path_or_obj, str) and os.path.exists(path_or_obj):
                with open(path_or_obj, "rb") as f:
                    img_bytes = f.read()
            else:
                # If API changed, fallback to text card
                raise RuntimeError("Unexpected enkanetworkcard output")
            await update.message.reply_photo(photo=img_bytes, caption=f"Enka Banner – UID {uid}")
            return
        except Exception as e:
            logger.warning(f"enkanetworkcard failed: {e}")

    # Last resort: simple text card
    img_bytes = await render_fallback_card_text(uid, "Enka Card (fallback)", ["قم بتثبيت enkacard أو enkanetworkcard لتوليد بطاقات رسومية."])
    await update.message.reply_photo(photo=img_bytes)

# ----------------------------
# Main
# ----------------------------

async def main_async():
    require_token()
    await init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

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
    await app.run_polling(close_loop=False)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        pass
