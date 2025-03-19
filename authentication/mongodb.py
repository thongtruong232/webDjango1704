from pymongo import MongoClient
from django.conf import settings

def get_db():
    print("MONGODB_URI:", settings.MONGODB_URI)
    client = MongoClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DATABASE]
    return db, client

def get_collection_handle(collection_name):
    db, client = get_db()
    return db[collection_name], client 