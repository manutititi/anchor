import re
import os
from pymongo import MongoClient

# Conexión propia
mongo_uri = os.getenv("MONGO_URI", "mongodb://ancadmin:ancpass@mongodb:27017/")
mongo_db = os.getenv("MONGO_DB", "anchor")
client = MongoClient(mongo_uri)
db = client[mongo_db]

# Diccionario de operadores
OPERATORS = {
    "=": lambda f, v: {f: {"$in": [v]} if f == "groups" else v},
    "!=": lambda f, v: {f: {"$nin": [v]} if f == "groups" else {"$ne": v}},
    "~": lambda f, v: {f: {"$regex": v, "$options": "i"}},
    "!~": lambda f, v: {f: {"$not": {"$regex": v, "$options": "i"}}}
}

def parse_to_mongo_query(expr: str) -> dict | None:
    print(f"[DEBUG] Parsing filter: {expr}")
    if not expr:
        return {}

    try:
        if "(" in expr or ")" in expr:
            return None  # No soportamos paréntesis aún

        logic = "AND" if " AND " in expr else "OR" if " OR " in expr else None
        clauses = [expr] if not logic else expr.split(f" {logic} ")

        mongo_clauses = []
        for clause in clauses:
            match = re.match(r'([a-zA-Z0-9_.]+)\s*(=|!=|~|!~)\s*("[^"]+"|\S+)', clause.strip())
            if not match:
                return None
            field, op, raw_val = match.groups()
            val = raw_val.strip('"')
            if op not in OPERATORS:
                return None
            mongo_clauses.append(OPERATORS[op](field, val))

        if logic == "AND":
            return {"$and": mongo_clauses}
        elif logic == "OR":
            return {"$or": mongo_clauses}
        else:
            return mongo_clauses[0]
    except Exception as e:
        print(f"[ERROR] parse_to_mongo_query: {e}")
        return None

def query_collection(collection_name: str, filter_expr: str = "", projection: dict = None) -> list:
    """
    Consulta MongoDB usando filtro expresivo. Devuelve lista de documentos.
    """
    try:
        collection = db[collection_name]
        print(f"[DEBUG] Raw filter_expr: {filter_expr}")
        query = parse_to_mongo_query(filter_expr)
        print(f"[DEBUG] Parsed query: {query}")

        if projection:
            return list(collection.find(query, projection))
        else:
            return list(collection.find(query))
    except Exception as e:
        print(f"[ERROR] query_collection: {e}")
        return []






