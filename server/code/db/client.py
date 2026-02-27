from pymongo import MongoClient
from config import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI)
    return _client


def get_db():
    return get_client()[settings.MONGO_DB]


def get_collection(name: str):
    return get_db()[name]


def close_client():
    global _client
    if _client is not None:
        _client.close()
        _client = None
