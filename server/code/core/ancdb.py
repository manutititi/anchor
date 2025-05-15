# code/core/ancdb.py
from pymongo import MongoClient
from pydantic import RootModel
from typing import Any
from code.auth.session import get_current_groups, get_current_user
from collections import OrderedDict
from code.core.utils import now_tz
import json
import os
from core.filter import query_collection



class ancDB:
    def __init__(self):
        mongo_uri = os.getenv("MONGO_URI", "mongodb://ancadmin:ancpass@mongodb:27017/")
        mongo_db = os.getenv("MONGO_DB", "anchor")
        self.client = MongoClient(mongo_uri)
        self.db = self.client[mongo_db]

    def get_collection(self, name):
        return self.db[name]

    def test_connection(self):
        try:
            self.client.admin.command("ping")
            print("[DEBUG] MongoDB connection successful")
            return True
        except Exception as e:
            print(f"[DEBUG] MongoDB connection failed: {e}")
            return False

    def upload_anchor(self, filename: str, data: dict, user: str):
        collection = self.get_collection("anchors")

        if "name" not in data or not data["name"]:
            data["name"] = os.path.splitext(filename)[0]

        name = data["name"]
        existing = collection.find_one({"name": name})
        now = now_tz()

        if not existing:
            data["created_at"] = now
            data["created_by"] = user

        data["last_updated"] = now
        data["updated_by"] = user

        # Ordenar claves
        reordered = OrderedDict()
        for key in ["type", "name", "groups"]:
            if key in data:
                reordered[key] = data[key]
        for k, v in data.items():
            if k not in reordered:
                reordered[k] = v

        result = collection.replace_one({"name": name}, reordered, upsert=True)
        return {
            "status": "ok",
            "anchor": name,
            "inserted": result.upserted_id is not None,
            "user": user
        }

   

    
    