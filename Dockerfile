# استخدم نسخة بايثون محددة
FROM python:3.11-slim

# تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ الملفات المطلوبة
COPY requirements.txt .
COPY bot.py .
COPY Procfile .

# تثبيت المكتبات
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# تعيين الأمر الافتراضي لتشغيل البوت
CMD ["python", "bot.py"]
