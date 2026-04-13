"""
Anchor CLI entry point.

Registered as the `anc` binary via pyproject.toml:
    [project.scripts]
    anc = "anchor.cli:app"
"""

from __future__ import annotations

import typer

from anchor.commands import cp, cr, login, ls, mask, path, pull, push, rc, set
from anchor.commands.go import anchor_type, go
from anchor.commands.secret import app as secret_app
from anchor.commands.vpn import app as vpn_app

app = typer.Typer(
    name="anc",
    help="Anchor CLI — manage paths, secrets, and infrastructure anchors.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="rich",
)

# ------------------------------------------------------------------
# Top-level commands
# ------------------------------------------------------------------
app.command("login")(login.login)
app.command("set")(set.set_anchor)
app.command("pull")(pull.pull)
app.command("push")(push.push)
app.command("ls")(ls.ls)
app.command("path")(path.path)
app.command("go")(go)
app.command("cr")(cr.cr)
app.command("rc")(rc.rc)
app.command("cp")(cp.cp)
app.command("mask")(mask.mask)

# Internal — used by the shell wrapper (anchor/shell/anc.sh) to route
# bare `anc <name>` calls without side effects.
app.command("_type", hidden=True)(anchor_type)

# ------------------------------------------------------------------
# Subgroups
# ------------------------------------------------------------------
app.add_typer(secret_app, name="secret")
app.add_typer(vpn_app, name="vpn")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
