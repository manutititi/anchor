import sys
import json
import os
import re

def get_nested(d, key):
    parts = key.split(".")
    for part in parts:
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d

def normalize_value(value):
    """Convierte valores booleanos, pero no toca strings numéricos."""
    if isinstance(value, str):
        v = value.lower()
        if v == "true":
            return True
        if v == "false":
            return False
    return value

def expr_to_lambda(expr_str):
    expr_str = re.sub(r"\s+(AND|and)\s+", " and ", expr_str, flags=re.IGNORECASE)
    expr_str = re.sub(r"\s+(OR|or)\s+", " or ", expr_str, flags=re.IGNORECASE)

    pattern = re.compile(r'([a-zA-Z0-9_.]+)\s*(!=|=|~|!~)\s*("[^"]+"|\'[^\']+\'|[^\s()]+)')
    var_map = {}
    replacements = []

    for i, match in enumerate(pattern.finditer(expr_str)):
        key, op, val = match.groups()
        var_name = f"_v{i}"
        start, end = match.span()
        replacements.append((start, end, var_name))
        val = val.strip('"').strip("'")
        var_map[var_name] = (key.strip(), op.strip(), normalize_value(val))

    parts = []
    last_index = 0
    for start, end, var_name in replacements:
        parts.append(expr_str[last_index:start])
        parts.append(var_name)
        last_index = end
    parts.append(expr_str[last_index:])
    expr_final = "".join(parts)

    def matcher(data):
        env = {}
        for var_name, (key, op, expected) in var_map.items():
            actual = get_nested(data, key)
            if op == "=":
                env[var_name] = expected in actual if isinstance(actual, list) else actual == expected
            elif op == "!=":
                env[var_name] = expected not in actual if isinstance(actual, list) else actual != expected
            elif op == "~":
                env[var_name] = expected in str(actual) if actual is not None else False
            elif op == "!~":
                env[var_name] = expected not in str(actual) if actual is not None else True
        try:
            return eval(expr_final, {}, env)
        except Exception as e:
            print(f"[filter error] {e}")
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
