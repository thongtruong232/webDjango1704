from pymongo import MongoClient
from django.conf import settings
import logging
from typing import Optional, Tuple
from pymongo.collection import Collection
from pymongo.database import Database
import dns.resolver

logger = logging.getLogger(__name__)

# Cấu hình DNS resolver
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8', '8.8.4.4']

class MongoDBConnection:
    def __init__(self):
        self.client = None
        self.db = None

    def __enter__(self):
        try:
            self.client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=5000,  # Timeout 5 giây
                connectTimeoutMS=5000,
                socketTimeoutMS=5000
            )
            self.db = self.client[settings.MONGODB_DATABASE]
            # Test kết nối
            self.client.server_info()
            return self
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {str(e)}")
            if self.client:
                self.client.close()
            return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            self.client.close()

    def get_collection(self, collection_name: str) -> Optional[Collection]:
        if self.db is not None:
            return self.db[collection_name]
        return None

def get_collection_handle(collection_name: str) -> Tuple[Optional[Collection], Optional[MongoClient]]:
    """
    Get a MongoDB collection handle and client connection.
    Args:
        collection_name (str): Name of the collection to get
    Returns:
        Tuple[Optional[Collection], Optional[MongoClient]]: A tuple containing (collection, client),
        or (None, None) if connection fails
    """
    try:
        client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,  # Timeout 5 giây
            connectTimeoutMS=5000,
            socketTimeoutMS=5000
        )
        db = client[settings.MONGODB_DATABASE]
        collection = db[collection_name]
        return collection, client
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {str(e)}")
        return None, None 