def get_nested(d, key):
    parts = key.split(".")
    for part in parts:
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
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

def matches_filter(data: dict, filter_str: str) -> bool:
    if not filter_str:
        return True

    conditions = [f.strip() for f in filter_str.split(",") if "=" in f]

    for cond in conditions:
        key, expected = cond.split("=", 1)
        expected = normalize_value(expected)
        value = get_nested(data, key)

        if value != expected:
            return False

    return True
