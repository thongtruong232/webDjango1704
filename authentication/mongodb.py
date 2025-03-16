from pymongo import MongoClient
from django.conf import settings

def get_db_handle():
    client = MongoClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DATABASE]
    return db, client

def get_collection_handle(collection_name):
    db, client = get_db_handle()
    return db[collection_name], client 