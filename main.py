import os
import logging
import sqlite3
import asyncio
import threading
from typing import Dict, Optional
from telebot import TeleBot, types
import genshin
from enkanetwork import EnkaNetworkAPI
import aiohttp
from io import BytesIO

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تهيئة البوت
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logger.error("لم يتم تعيين BOT_TOKEN في متغيرات البيئة")
    exit(1)

bot = TeleBot(TOKEN)

# تهيئة قاعدة البيانات
def init_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            genshin_uid INTEGER,
            cookie TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# وظائف مساعدة لقاعدة البيانات
def get_user_data(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    c.execute("SELECT genshin_uid, cookie FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return {"genshin_uid": result[0], "cookie": result[1]}
    return None

def save_user_data(user_id: int, genshin_uid: int, cookie: str = None):
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    
    if cookie:
        c.execute(
            "INSERT OR REPLACE INTO users (user_id, genshin_uid, cookie) VALUES (?, ?, ?)",
            (user_id, genshin_uid, cookie)
        )
    else:
        c.execute(
            "INSERT OR REPLACE INTO users (user_id, genshin_uid) VALUES (?, ?)",
            (user_id, genshin_uid)
        )
    
    conn.commit()
    conn.close()

# تشغيل الأوامر غير المتزامنة في خلفية
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# معالجة الأوامر
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    user_markup.row('👤 بروفايلي', '🎮 شخصياتي')
    user_markup.row('🖼️ كروت الشخصيات', '⚙️ إعدادات')
    
    welcome_text = """
مرحباً بك في بوت Genshin Impact! 🎮

الأوامر المتاحة:
/start - عرض هذه الرسالة
/profile - عرض معلومات لاعبك
/characters - عرض شخصياتك
/card - إنشاء كارت لشخصية معينة
/set_uid [UID] - تعيين UID الخاص بك
/resin - فحص الريسِن الحالي
/set_cookie [cookie] - تعيين cookie للوصول لبياناتك
"""

    bot.send_message(message.chat.id, welcome_text, reply_markup=user_markup)

@bot.message_handler(commands=['set_uid'])
def set_uid_command(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "يرجى إضافة UID بعد الأمر: /set_uid 700000000")
            return
        
        uid = int(args[1])
        save_user_data(message.from_user.id, uid)
        
        bot.reply_to(message, f"تم حفظ UID: {uid} بنجاح! ✅")
    
    except ValueError:
        bot.reply_to(message, "UID يجب أن يكون رقماً صحيحاً")
    except Exception as e:
        logger.error(f"Error in set_uid: {e}")
        bot.reply_to(message, "حدث خطأ أثناء حفظ UID")

@bot.message_handler(commands=['profile'])
def profile_command(message):
    try:
        user_data = get_user_data(message.from_user.id)
        if not user_data or not user_data['genshin_uid']:
            bot.reply_to(message, "لم تقم بتعيين UID بعد. استخدم /set_uid [UID]")
            return
        
        # تشغيل الوظيفة غير المتزامنة في خيط منفصل
        def get_profile():
            async def async_get_profile():
                async with aiohttp.ClientSession() as session:
                    enka = EnkaNetworkAPI(session=session)
                    await enka.update_assets()
                    return await enka.fetch_user(user_data['genshin_uid'])
            return run_async(async_get_profile())
        
        player = get_profile()
        
        profile_text = f"""
🎪 بروفايل اللاعب:
الاسم: {player.nickname}
المستوى: {player.level}
العالم: {player.world_level}
الإنجازات: {player.achievements}
أبراج: {player.abyss_floor}-{player.abyss_room}
عدد الشخصيات: {len(player.characters)}
        """
        
        bot.reply_to(message, profile_text)
    
    except Exception as e:
        logger.error(f"Error in profile: {e}")
        if "Player not found" in str(e) or "404" in str(e):
            bot.reply_to(message, "لم يتم العثور على اللاعب. تأكد من صحة UID وإعدادات الخصوصية")
        else:
            bot.reply_to(message, "حدث خطأ أثناء جلب البيانات")

@bot.message_handler(commands=['characters'])
def characters_command(message):
    try:
        user_data = get_user_data(message.from_user.id)
        if not user_data or not user_data['genshin_uid']:
            bot.reply_to(message, "لم تقم بتعيين UID بعد. استخدم /set_uid [UID]")
            return
        
        def get_chars():
            async def async_get_chars():
                client = genshin.Client()
                if user_data.get('cookie'):
                    client.set_cookies(user_data['cookie'])
                return await client.get_characters(user_data['genshin_uid'])
            return run_async(async_get_chars())
        
        characters = get_chars()
        
        characters_text = "شخصياتك: \n\n"
        for char in characters[:10]:  # عرض أول 10 شخصيات فقط
            characters_text += f"{char.name} - المستوى {char.level} - ⭐{char.rarity}\n"
        
        if len(characters) > 10:
            characters_text += f"\nو {len(characters) - 10} شخصية أخرى..."
        
        bot.reply_to(message, characters_text)
    
    except Exception as e:
        logger.error(f"Error in characters: {e}")
        bot.reply_to(message, "حدث خطأ أثناء جلب الشخصيات")

@bot.message_handler(commands=['card'])
def card_command(message):
    try:
        user_data = get_user_data(message.from_user.id)
        if not user_data or not user_data['genshin_uid']:
            bot.reply_to(message, "لم تقم بتعيين UID بعد. استخدم /set_uid [UID]")
            return
        
        # إرسال رسالة انتظار
        wait_msg = bot.reply_to(message, "⏳ جاري إنشاء الكارت...")
        
        def generate_card():
            async def async_generate_card():
                async with aiohttp.ClientSession() as session:
                    enka = EnkaNetworkAPI(session=session)
                    await enka.update_assets()
                    player = await enka.fetch_user(user_data['genshin_uid'])
                    
                    if not player.characters:
                        return None
                    
                    # توليد صورة للشخصية الأولى
                    character = player.characters[0]
                    return await character.card.render()
            return run_async(async_generate_card())
        
        image = generate_card()
        
        if image is None:
            bot.edit_message_text("لا توجد شخصيات لعرضها", message.chat.id, wait_msg.message_id)
            return
        
        # حفظ الصورة مؤقتاً وإرسالها
        with BytesIO() as buffer:
            image.save(buffer, format="PNG")
            buffer.seek(0)
            bot.delete_message(message.chat.id, wait_msg.message_id)
            bot.send_photo(
                message.chat.id, 
                photo=buffer, 
                caption=f"كارت الشخصية | تم الإنشاء"
            )
    
    except Exception as e:
        logger.error(f"Error in card: {e}")
        bot.reply_to(message, "حدث خطأ أثناء إنشاء الكارت")

@bot.message_handler(commands=['resin'])
def resin_command(message):
    try:
        user_data = get_user_data(message.from_user.id)
        if not user_data or not user_data['genshin_uid']:
            bot.reply_to(message, "لم تقم بتعيين UID بعد. استخدم /set_uid [UID]")
            return
        
        # إذا لم يكن هناك cookie، نطلب من المستخدم إضافته
        if not user_data.get('cookie'):
            bot.reply_to(
                message, 
                "لم يتم تعيين cookie. لإضافة cookie استخدم:\n/set_cookie [cookie_text]\n\nملاحظة: يمكن الحصول على cookie من موقع Hoyolab"
            )
            return
        
        def get_notes():
            async def async_get_notes():
                client = genshin.Client()
                client.set_cookies(user_data['cookie'])
                return await client.get_notes(user_data['genshin_uid'])
            return run_async(async_get_notes())
        
        notes = get_notes()
        
        # تحويل وقت الاسترداد إلى تنسيق مقروء
        def format_time(seconds):
            if seconds <= 0:
                return "مكتمل"
            hours, remainder = divmod(seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{int(hours)} ساعة {int(minutes)} دقيقة"
        
        resin_text = f"""
⚡ الريسِن الحالي: {notes.current_resin}/{notes.max_resin}
⏳ وقت الامتلاء: {format_time(notes.remaining_resin_recovery_time)}

🎯 الباوند: {notes.current_realm_currency}/{notes.max_realm_currency}
⏳ وقت امتلاء الباوند: {format_time(notes.remaining_realm_currency_recovery_time)}

📦 المهمات اليومية: {notes.completed_commissions}/{notes.max_commissions}
🔄 إعادة التدوير: {notes.remaining_resin_discounts} مرات متبقية
        """
        
        bot.reply_to(message, resin_text)
    
    except Exception as e:
        logger.error(f"Error in resin: {e}")
        bot.reply_to(message, "حدث خطأ أثناء جلب بيانات الريسِن. تأكد من صحة cookie")

@bot.message_handler(commands=['set_cookie'])
def set_cookie_command(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "يرجى إضافة cookie بعد الأمر: /set_cookie [cookie_text]")
            return
        
        cookie = args[1]
        user_data = get_user_data(message.from_user.id)
        
        if not user_data or not user_data['genshin_uid']:
            bot.reply_to(message, "يجب تعيين UID أولاً باستخدام /set_uid [UID]")
            return
        
        save_user_data(message.from_user.id, user_data['genshin_uid'], cookie)
        bot.reply_to(message, "تم حفظ cookie بنجاح! ✅")
    
    except Exception as e:
        logger.error(f"Error in set_cookie: {e}")
        bot.reply_to(message, "حدث خطأ أثناء حفظ cookie")

# معالجة الأزرار
@bot.message_handler(func=lambda message: message.text == '👤 بروفايلي')
def profile_button(message):
    profile_command(message)

@bot.message_handler(func=lambda message: message.text == '🎮 شخصياتي')
def characters_button(message):
    characters_command(message)

@bot.message_handler(func=lambda message: message.text == '🖼️ كروت الشخصيات')
def card_button(message):
    card_command(message)

@bot.message_handler(func=lambda message: message.text == '⚙️ إعدادات')
def settings_button(message):
    user_data = get_user_data(message.from_user.id)
    
    if user_data and user_data['genshin_uid']:
        settings_text = f"""
الإعدادات الحالية:
UID: {user_data['genshin_uid']}
Cookie: {'✅ معين' if user_data.get('cookie') else '❌ غير معين'}
        """
    else:
        settings_text = "لم تقم بتعيين UID بعد. استخدم /set_uid [UID]"
    
    bot.reply_to(message, settings_text)

# معالجة الأخطاء العامة
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "لم أفهم طلبك. استخدم الأزرار أو الأوامر المتاحة.")

# تشغيل البوت
if __name__ == '__main__':
    logger.info("Starting bot...")
    bot.infinity_polling()
