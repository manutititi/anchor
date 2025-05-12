import sys
import json
import os
import re

def get_nested(d, key):
    parts = key.split(".")
    for part in parts:
        if not isinstance(d, dict) or part not in d:
            return None
        d = part = d[part]
    return d

def normalize_value(value):
    """Convierte 'true' → True, '123' → 123, etc."""
    if isinstance(value, str):
        v = value.lower()
        if v == "true":
            return True
        if v == "false":
            return False
        if v.isdigit():
            return int(v)
    return value

def expr_to_lambda(expr_str):
    """
    Convierte una expresión como:
        (env=dev OR env!=stage) AND project~demo
    En una función que evalúa un dict.
    """
    # Reemplaza operadores lógicos
    expr_str = expr_str.replace(" AND ", " and ").replace(" OR ", " or ")

    # Soporta múltiples operadores: =, !=, ~, !~
    pattern = re.compile(r'([a-zA-Z0-9_.]+)\s*(!=|=|~|!~)\s*("[^"]+"|[^\s()]+)')
    var_map = {}

    for i, (key, op, val) in enumerate(pattern.findall(expr_str)):
        var_name = f"_v{i}"
        full_expr = f"{key}{op}{val}"
        expr_str = expr_str.replace(full_expr, var_name)
        var_map[var_name] = (key.strip(), op.strip(), normalize_value(val.strip('"')))

    def matcher(data):
        env = {}
        for var_name, (key, op, expected) in var_map.items():
            actual = get_nested(data, key)
            if op == "=":
                if isinstance(actual, list):
                    env[var_name] = expected in actual
                else:
                    env[var_name] = (actual == expected)
            elif op == "!=":
                if isinstance(actual, list):
                    env[var_name] = expected not in actual
                else:
                    env[var_name] = (actual != expected)
            elif op == "~":
                env[var_name] = expected in str(actual) if actual is not None else False
            elif op == "!~":
                env[var_name] = expected not in str(actual) if actual is not None else True
        try:
            return eval(expr_str, {}, env)
        except Exception:
            return False

    return matcher

def matches_filter(data: dict, filter_str: str) -> bool:
    if not filter_str:
        return True
    try:
        matcher = expr_to_lambda(filter_str)
        return matcher(data)
    except Exception:
        return False

def load_all_anchors(anchor_dir: str) -> dict:
    anchors = {}
    for fname in os.listdir(anchor_dir):
        if fname.endswith(".json"):
            name = fname[:-5]
            try:
                with open(os.path.join(anchor_dir, fname), "r") as f:
                    anchors[name] = json.load(f)
            except Exception:
                continue
    return anchors

def filter_anchors(filter_str=None) -> dict:
    anchor_dir = os.environ.get("ANCHOR_DIR", "./data")
    anchors = load_all_anchors(anchor_dir)
    return {name: data for name, data in anchors.items() if matches_filter(data, filter_str)}

# CLI fallback
if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    matched = filter_anchors(query)
    for name in matched:
        print(name)
