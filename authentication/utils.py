from pymongo import MongoClient
from django.conf import settings
import logging
from typing import Optional
from pymongo.collection import Collection
from pymongo.database import Database

logger = logging.getLogger(__name__)

class MongoDBConnection:
    def __init__(self):
        self.client = None
        self.db = None

    def __enter__(self):
        try:
            self.client = MongoClient(settings.MONGODB_URI)
            self.db = self.client[settings.MONGODB_DATABASE]
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
        if self.db:
            return self.db[collection_name]
        return None 