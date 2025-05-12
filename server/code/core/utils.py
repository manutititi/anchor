import re

def get_nested(d, key):
    """
    Permite acceder a claves anidadas usando notación punto, ej: endpoint.base_url
    """
    parts = key.split(".")
    for part in parts:
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def normalize_value(value):
    """
    Convierte strings comunes a tipos útiles: bool, int, etc.
    """
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
    Convierte una expresión tipo: env=prod AND project~web
    en una función que evalúa un dict.
    """
    expr_str = expr_str.replace(" AND ", " and ").replace(" OR ", " or ")
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
                env[var_name] = (actual == expected)
            elif op == "!=":
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
    """
    Evalúa si un diccionario cumple con una expresión de filtro.
    """
    if not filter_str:
        return True
    try:
        matcher = expr_to_lambda(filter_str)
        return matcher(data)
    except Exception:
        return False
