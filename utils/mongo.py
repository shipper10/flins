from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.genshin_bot

users_collection = db.users
logs_collection = db.logs
