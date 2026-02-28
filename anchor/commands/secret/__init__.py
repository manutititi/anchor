"""
anc secret — manage encrypted secrets in the vault.

Subcommands:
    anc secret ls [prefix]           List visible secrets
    anc secret get <path>            Print a secret value
    anc secret push <path>           Create a new secret
    anc secret update <path>         Update (new version)
    anc secret del <path>            Delete a secret
"""

from __future__ import annotations

import typer

from anchor.commands.secret import del_cmd, get, ls, push, update

app = typer.Typer(
    name="secret",
    help="Manage encrypted secrets in the vault.",
    no_args_is_help=True,
)

app.command("ls")(ls.ls)
app.command("get")(get.get)
app.command("push")(push.push)
app.command("update")(update.update)
app.command("del")(del_cmd.del_secret)
