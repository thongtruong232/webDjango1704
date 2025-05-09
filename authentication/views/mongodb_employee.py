from pymongo import MongoClient
from django.conf import settings
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

# Singleton MongoDB client
_mongo_client = None

def get_mongo_client():
    """Get or create MongoDB client singleton"""
    global _mongo_client
    if _mongo_client is None:
        try:
            _mongo_client = MongoClient(settings.MONGODB_URI)
        except Exception as e:
            logger.error(f"Error creating MongoDB client: {str(e)}")
            return None
    return _mongo_client

def get_collection_handle_employee(collection_name):
    """Get MongoDB collection handle"""
    try:
        client = get_mongo_client()
        if client is None:
            return None
            
        db = client[settings.MONGODB_DATABASE]
        collection = db[collection_name]
        return collection
    except Exception as e:
        logger.error(f"Error getting collection handle: {str(e)}")
        return None

def get_collection(collection_name):
    connection = get_mongo_client()
    return connection[settings.MONGODB_DATABASE][collection_name]

def convert_to_object_id(id_str):
    try:
        return ObjectId(id_str)
    except:
        return None 