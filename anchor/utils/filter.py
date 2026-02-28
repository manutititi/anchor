"""
Filter expression parser for anchor queries.

Syntax:
    key=value           exact match (or list membership)
    key!=value          not equal
    key~value           substring match
    key!~value          substring not present
    expr AND expr       logical AND
    expr OR expr        logical OR

Nested keys use dot notation: git.branch=main, meta.env=prod

No eval() — parsed into an explicit AST and walked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class Condition:
    key: str
    op: str   # "=" | "!=" | "~" | "!~"
    val: str


@dataclass
class AndNode:
    left: "Node"
    right: "Node"


@dataclass
class OrNode:
    left: "Node"
    right: "Node"


Node = Condition | AndNode | OrNode


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def _get_nested(data: dict, key: str) -> Any:
    """Resolve dot-notation keys: 'git.branch' → data['git']['branch']."""
    for part in key.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data


def _normalize(value: str) -> Any:
    """Convert 'true'/'false' strings to bool; leave everything else as str."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def _eval_condition(data: dict, cond: Condition) -> bool:
    actual = _get_nested(data, cond.key)
    expected = _normalize(cond.val)

    if cond.op == "=":
        if isinstance(actual, list):
            return expected in actual
        return actual == expected

    if cond.op == "!=":
        if isinstance(actual, list):
            return expected not in actual
        return actual != expected

    if cond.op == "~":
        return actual is not None and expected in str(actual)

    if cond.op == "!~":
        return actual is None or expected not in str(actual)

    return False


def _eval_node(data: dict, node: Node) -> bool:
    if isinstance(node, Condition):
        return _eval_condition(data, node)
    if isinstance(node, AndNode):
        return _eval_node(data, node.left) and _eval_node(data, node.right)
    if isinstance(node, OrNode):
        return _eval_node(data, node.left) or _eval_node(data, node.right)
    return False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_COND_RE = re.compile(
    r'([a-zA-Z0-9_.]+)\s*(!=|!~|=|~)\s*(?:"([^"]+)"|\'([^\']+)\'|(\S+))'
)


def _parse_tokens(expr: str) -> list[str | Condition]:
    """Tokenize expression into Conditions and AND/OR strings."""
    tokens: list[str | Condition] = []
    # Split on AND/OR keeping the delimiters
    parts = re.split(r'\s+(AND|OR)\s+', expr, flags=re.IGNORECASE)
    for part in parts:
        upper = part.strip().upper()
        if upper in ("AND", "OR"):
            tokens.append(upper)
        else:
            m = _COND_RE.match(part.strip())
            if not m:
                raise ValueError(f"Invalid filter expression: '{part.strip()}'")
            key, op = m.group(1), m.group(2)
            val = m.group(3) or m.group(4) or m.group(5) or ""
            tokens.append(Condition(key=key, op=op, val=val))
    return tokens


def _tokens_to_ast(tokens: list[str | Condition]) -> Node:
    """Build AST from tokens, respecting OR < AND precedence."""
    # OR has lower precedence: split on OR first, then AND within each segment
    if not tokens:
        raise ValueError("Empty filter expression")

    # Split by OR at top level
    or_segments: list[list] = [[]]
    for token in tokens:
        if token == "OR":
            or_segments.append([])
        else:
            or_segments[-1].append(token)

    def build_and(segment: list) -> Node:
        if not segment:
            raise ValueError("Empty AND segment")
        nodes: list[Node] = []
        for item in segment:
            if item == "AND":
                continue
            if isinstance(item, Condition):
                nodes.append(item)
        if not nodes:
            raise ValueError("No conditions in AND segment")
        result = nodes[0]
        for n in nodes[1:]:
            result = AndNode(left=result, right=n)
        return result

    or_nodes = [build_and(seg) for seg in or_segments]
    result = or_nodes[0]
    for n in or_nodes[1:]:
        result = OrNode(left=result, right=n)
    return result


def parse_filter(expr: str) -> Callable[[dict], bool]:
    """Parse a filter expression string and return a predicate function."""
    expr = expr.strip()
    if not expr:
        return lambda _: True
    tokens = _parse_tokens(expr)
    ast = _tokens_to_ast(tokens)

    def predicate(data: dict) -> bool:
        try:
            return _eval_node(data, ast)
        except Exception:
            return False

    return predicate


def matches_filter(data: dict, expr: str) -> bool:
    """Convenience: return True if data matches the filter expression."""
    if not expr:
        return True
    return parse_filter(expr)(data)
