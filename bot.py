from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN
from handlers.register import register_handler
from handlers.profile import profile_handler
from handlers.characters import characters_handler
from handlers.abyss import abyss_handler
from handlers.resin import resin_handler
from handlers.resources_diary import resources_diary_handler
from handlers.daily_rewards import daily_rewards_handler

app = ApplicationBuilder().token(BOT_TOKEN).build()

# تسجيل handlers
app.add_handler(register_handler())
app.add_handler(profile_handler())
app.add_handler(characters_handler())
app.add_handler(abyss_handler())
app.add_handler(resin_handler())

# handlers التي ترجع قائمة handlers
for h in resources_diary_handler():
    app.add_handler(h)
for h in daily_rewards_handler():
    app.add_handler(h)

app.run_polling()
