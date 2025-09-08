from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN
from handlers.register import register_handler
# استيراد باقي الملفات: profile, characters, abyss, resin, resources_diary, daily_rewards

app = ApplicationBuilder().token(BOT_TOKEN).build()

# إضافة handlers
app.add_handler(register_handler())
# app.add_handler(profile_handler())
# app.add_handler(characters_handler())
# app.add_handler(abyss_handler())
# app.add_handler(resin_handler())
# app.add_handler(resources_diary_handler())
# app.add_handler(daily_rewards_handler())

app.run_polling()
