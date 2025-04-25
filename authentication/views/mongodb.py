from pymongo import MongoClient
from django.conf import settings
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

class MongoDBConnection:
    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBConnection, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            try:
                self._client = MongoClient(
                    settings.MONGODB_URI,
                    username=settings.MONGODB_USERNAME,
                    password=settings.MONGODB_PASSWORD,
                    retryWrites=True,
                    w='majority'
                )
                self._db = self._client[settings.MONGODB_DATABASE]
                # Test connection
                self._client.server_info()
                logger.info("Successfully connected to MongoDB")
            except Exception as e:
                logger.error(f"Error connecting to MongoDB: {e}")
                raise

    @property
    def db(self):
        return self._db

    @property
    def client(self):
        return self._client

    def get_collection(self, collection_name):
        return self._db[collection_name]

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {e}")
            finally:
                self._client = None
                self._db = None

def get_mongodb_connection():
    return MongoDBConnection()

def get_collection(collection_name):
    connection = get_mongodb_connection()
    return connection.get_collection(collection_name)

def get_collection_handle(collection_name):
    """Get MongoDB collection handle"""
    try:
        connection = get_mongodb_connection()
        collection = connection.get_collection(collection_name)
        return collection
    except Exception as e:
        logger.error(f"Error getting collection handle: {e}")
        return None

def convert_to_object_id(id_str):
    try:
        return ObjectId(id_str)
    except:
        return None 