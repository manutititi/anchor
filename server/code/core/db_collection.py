from pymongo import MongoClient
import os

def get_mongo_collection(collection_name: str):
    """
    Connect with mongo for collection
    """
    mongo_uri = os.getenv("MONGO_URI", "mongodb://ancadmin:ancpass@mongodb:27017/")
    mongo_db = os.getenv("MONGO_DB", "anchor")

    client = MongoClient(mongo_uri)
    db = client[mongo_db]
    return db[collection_name]
