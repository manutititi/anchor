"""
anc mask — sanitize text by replacing sensitive data with placeholders.

Usage:
    cat error.log | anc mask company              # apply mask rules
    cat error.log | anc mask company --unmask      # reverse using saved mapping
    anc mask company --rules                       # show current rules
    anc mask company --add "Acme S\\.L\\." COMPANY # add a rule
    anc mask company --rm COMPANY                  # remove a rule
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from anchor.store import load_anchor, save_anchor
from anchor.utils.output import err, info, out, success

# ---------------------------------------------------------------------------
# Built-in patterns (inherited from maskit)
# ---------------------------------------------------------------------------

BUILTIN_PATTERNS: dict[str, str] = {
    "ip": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "email": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "phone": r"(?<!\w)\+?\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}(?!\w)",
    "iban": r"\b[A-Z]{2}\d{2}(?:\s?\d{4}){3,}\d{0,4}\b",
    "card": r"\b(?:\d[ \-]*?){13,19}\b",
}

ALL_BUILTINS = list(BUILTIN_PATTERNS.keys())

AI_HEADER = (
    "# NOTE: This text has been sanitized. Placeholders like [[ NAME ]] replace\n"
    "# sensitive data. Each placeholder is consistent — the same original value\n"
    "# always maps to the same placeholder throughout the text.\n\n"
)


# ---------------------------------------------------------------------------
# Core masking logic
# ---------------------------------------------------------------------------

def _apply_mask(text: str, anchor_data: dict) -> tuple[str, dict[str, str]]:
    """Apply mask rules to text. Returns (masked_text, mapping)."""
    mapping: dict[str, str] = {}  # original → placeholder

    # 1) User-defined rules (fixed placeholder per pattern)
    for rule in anchor_data.get("rules", []):
        try:
            regex = re.compile(rule["pattern"])
        except re.error as exc:
            print(f"# WARNING: invalid regex {rule['pattern']!r}: {exc}", file=sys.stderr)
            continue

        placeholder = f"[[ {rule['placeholder']} ]]"

        for match in regex.finditer(text):
            original = match.group()
            if original not in mapping:
                mapping[original] = placeholder

        text = regex.sub(lambda m: mapping.get(m.group(), m.group()), text)

    # 2) Built-in patterns (numbered placeholders per unique value)
    for builtin_name in anchor_data.get("builtin", []):
        pattern_str = BUILTIN_PATTERNS.get(builtin_name)
        if not pattern_str:
            continue

        regex = re.compile(pattern_str)
        label = builtin_name.upper()
        counter: dict[str, str] = {}  # track unique values for this builtin

        def _replace(m: re.Match, _label: str = label, _counter: dict = counter) -> str:
            val = m.group()
            if val in mapping:
                return mapping[val]
            if val not in _counter:
                n = len(_counter) + 1
                _counter[val] = f"[[ {_label}_{n} ]]"
                mapping[val] = _counter[val]
            return _counter[val]

        text = regex.sub(_replace, text)

    return text, mapping


def _apply_unmask(text: str, mapping: dict[str, str]) -> str:
    """Reverse a mask using a saved mapping."""
    # Sort by longest placeholder first to avoid partial replacements
    reverse = {v: k for k, v in mapping.items()}
    for placeholder in sorted(reverse, key=len, reverse=True):
        text = text.replace(placeholder, reverse[placeholder])

    # Strip AI header if present
    if text.startswith(AI_HEADER):
        text = text[len(AI_HEADER):]

    return text


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def mask(
    name: str = typer.Argument(help="Name of the mask anchor"),
    unmask: bool = typer.Option(False, "--unmask", "-u", help="Reverse mask using saved mapping"),
    show_rules: bool = typer.Option(False, "--rules", "-r", help="Show current mask rules"),
    add: Optional[str] = typer.Option(None, "--add", "-a", help="Add rule: --add 'regex=PLACEHOLDER'"),
    rm: Optional[str] = typer.Option(None, "--rm", help="Remove rule by placeholder name"),
) -> None:
    """Sanitize text by replacing sensitive data with consistent placeholders."""

    # -- Show rules ----------------------------------------------------------
    if show_rules:
        _show_rules(name)
        return

    # -- Add rule ------------------------------------------------------------
    if add is not None:
        if "=" not in add:
            err.print("[red]Usage:[/red] anc mask <name> --add 'pattern=PLACEHOLDER'")
            raise typer.Exit(1)
        pattern, placeholder = add.split("=", 1)
        if not pattern or not placeholder:
            err.print("[red]Usage:[/red] anc mask <name> --add 'pattern=PLACEHOLDER'")
            raise typer.Exit(1)
        _add_rule(name, pattern, placeholder)
        return

    # -- Remove rule ---------------------------------------------------------
    if rm is not None:
        _rm_rule(name, rm)
        return

    # -- Apply / Unmask (stdin required) -------------------------------------
    if sys.stdin.isatty():
        err.print("[yellow]Pipe text through stdin:[/yellow] cat file.log | anc mask " + name)
        raise typer.Exit(1)

    text = sys.stdin.read()

    data = _load_or_fail(name)

    if unmask:
        mapping = data.get("last_mapping", {})
        if not mapping:
            err.print(f"[red]No saved mapping for '{name}'.[/red] Run mask first.")
            raise typer.Exit(1)
        sys.stdout.write(_apply_unmask(text, mapping))
    else:
        masked, mapping = _apply_mask(text, data)
        data["last_mapping"] = mapping
        save_anchor(name, data)
        sys.stdout.write(AI_HEADER + masked)
        n_unique = len(mapping)
        if n_unique:
            print(f"# masked {n_unique} unique value(s)", file=sys.stderr)


# ---------------------------------------------------------------------------
# Rule management helpers
# ---------------------------------------------------------------------------

def _load_or_fail(name: str) -> dict:
    try:
        data = load_anchor(name)
    except FileNotFoundError:
        err.print(f"[red]Mask anchor '{name}' not found.[/red]")
        raise typer.Exit(1)
    if data.get("type") != "mask":
        err.print(f"[red]Anchor '{name}' is type '{data.get('type')}', not mask.[/red]")
        raise typer.Exit(1)
    return data


def _show_rules(name: str) -> None:
    data = _load_or_fail(name)
    table = Table(title=f"Mask rules: {name}", show_lines=False)
    table.add_column("Type", style="dim")
    table.add_column("Pattern", style="cyan")
    table.add_column("Placeholder", style="green")

    for rule in data.get("rules", []):
        table.add_row("custom", rule["pattern"], f"[[ {rule['placeholder']} ]]")

    for b in data.get("builtin", []):
        pat = BUILTIN_PATTERNS.get(b, "?")
        table.add_row("builtin", pat, f"[[ {b.upper()}_N ]]")

    if table.row_count == 0:
        err.print("[dim]No rules defined yet.[/dim]")
        info(f"Add one: [bold]anc mask {name} --add 'regex' PLACEHOLDER[/bold]")
        return

    out.print(table)


def _add_rule(name: str, pattern: str, placeholder: str) -> None:
    data = _load_or_fail(name)

    # Validate regex
    try:
        re.compile(pattern)
    except re.error as exc:
        err.print(f"[red]Invalid regex:[/red] {exc}")
        raise typer.Exit(1)

    placeholder = placeholder.upper().replace(" ", "_")

    # Check for duplicate placeholder
    for rule in data.get("rules", []):
        if rule["placeholder"] == placeholder:
            err.print(f"[yellow]Placeholder '{placeholder}' already exists — updating pattern.[/yellow]")
            rule["pattern"] = pattern
            save_anchor(name, data)
            success(f"Updated [bold]{placeholder}[/bold] → {pattern}")
            return

    data.setdefault("rules", []).append({"pattern": pattern, "placeholder": placeholder})
    save_anchor(name, data)
    success(f"Added [bold][[ {placeholder} ]][/bold] ← {pattern}")


def _rm_rule(name: str, placeholder: str) -> None:
    data = _load_or_fail(name)
    placeholder = placeholder.upper().replace(" ", "_")

    # Check builtin
    if placeholder.lower() in BUILTIN_PATTERNS:
        builtins = data.get("builtin", [])
        if placeholder.lower() in builtins:
            builtins.remove(placeholder.lower())
            save_anchor(name, data)
            success(f"Removed builtin [bold]{placeholder}[/bold]")
            return

    rules = data.get("rules", [])
    original_len = len(rules)
    data["rules"] = [r for r in rules if r["placeholder"] != placeholder]

    if len(data["rules"]) == original_len:
        err.print(f"[red]Placeholder '{placeholder}' not found.[/red]")
        raise typer.Exit(1)

    save_anchor(name, data)
    success(f"Removed [bold]{placeholder}[/bold]")
