#!/usr/bin/env python3
import argparse
import os
import sys

# Add path root  PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import subcommands
from commands import ls, meta, url, rc
from commands import set as set_cmd
from commands import delete
from commands import ldap as ldap_cmd
from commands import server as server_cmd  
from commands import push, pull
from core.commands.cr import handle_cr
from argparse import RawTextHelpFormatter
from core.commands.sible import handle_sible
from core.commands.edit import handle_edit
from core.commands.doc import generate_doc
from core.commands import secret




def load_help(command):
    help_path = os.path.join(os.path.dirname(__file__), "help", f"{command}.txt")
    if os.path.exists(help_path):
        with open(help_path, "r") as f:
            return f.read()
    return f"No help available for command '{command}'."



def main():
    parser = argparse.ArgumentParser(prog="anc", description="Anchor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ls
    ls_parser = subparsers.add_parser("ls", help="List anchors")
    ls_parser.add_argument("-f", "--filter", help="Filter in key=value format (supports AND/OR, ~, !=, etc.)")
    ls_parser.add_argument("-u", "--url", action="store_true", help="List anchors of type 'url'")
    ls_parser.add_argument("-e", "--env", action="store_true", help="List anchors of type 'env'")
    ls_parser.set_defaults(func=ls.run)


    # set
    set_parser = subparsers.add_parser("set", help="Create or update an anchor", description=load_help("set"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    set_parser.add_argument("name", nargs="?", help="Anchor name or path")
    set_parser.add_argument("--url", action="store_true", help="Create a URL-type anchor")
    set_parser.add_argument("--env", action="store_true", help="Create an environment anchor")
    set_parser.add_argument("--ldap", action="store_true", help="Create an LDAP anchor")
    set_parser.add_argument("--docker", action="store_true", help="Create a Docker-type anchor")
    set_parser.add_argument("--abs", action="store_true", help="Store absolute path (default: relative to ~)")
    set_parser.add_argument("--server", nargs="?", const="http://localhost:17017", help="Set server URL (default: localhost:17017)")
    set_parser.add_argument("base_url", nargs="?", help="Base URL or .env file depending on context")

        # Optionals LDAP
    set_parser.add_argument("--base-dn", help="Base DN for LDAP anchor")
    set_parser.add_argument("--bind-dn", help="Bind DN for LDAP admin")
    set_parser.add_argument("--bind-password", help="Bind password for LDAP")

        #ssh
    set_parser.add_argument("--ssh", nargs=2, metavar=("name", "user@host[:/path]"), help="Create SSH-type anchor: user@host[:/path]")
    set_parser.add_argument("-i", "--identity", help="SSH private key (optional)")
    set_parser.add_argument("--port", help="SSH port (default: 22)")

        # ansible
    set_parser.add_argument("--ansible", help="Create an Ansible anchor (name only)")
    set_parser.add_argument("--templates", "-t", nargs="+", help="Templates to include in the Ansible tasks")


    set_parser.set_defaults(func=set_cmd.run)


    # del
    del_parser = subparsers.add_parser("del", help="Delete anchors")
    del_parser.add_argument("name", nargs="?", help="Anchor name")
    del_parser.add_argument("-f", "--filter", help="Filter in key=value format")
    del_parser.set_defaults(func=delete.run)


    # meta
    meta_parser = subparsers.add_parser("meta", help="Update metadata", description=load_help("meta"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    meta_parser.add_argument("-f", "--filter", help="Filter anchors")
    meta_parser.add_argument("args", nargs="*", help="Anchor name followed by key=value pairs")
    meta_parser.add_argument("--del", nargs="+", dest="delete", help="Keys to delete")
    meta_parser.set_defaults(func=meta.run)


    # doc
    doc_parser = subparsers.add_parser("doc", help="Generate Markdown documentation for a given anchor.", description=load_help("doc"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    doc_parser.add_argument("name", help="Anchor name (or anchor filename without .json)")
    doc_parser.add_argument("--out", help="Write to a specific markdown file (default: <name>.md)")
    doc_parser.add_argument("--print", action="store_true", help="Print to stdout instead of writing to a file")
    doc_parser.set_defaults(func=lambda args: generate_doc(args.name, args.out, args.print))


    # url
    url_parser = subparsers.add_parser("url", help="Manage URL anchors")
    url_parser.add_argument("-a", "--add-route", action="store_true", help="Add route to URL anchor")
    url_parser.add_argument("-t", "--test", action="store_true", help="Test routes of a URL anchor")
    url_parser.add_argument("-d", "--del-route", dest="del_route", action="store_true", help="Delete a route from an anchor")
    url_parser.add_argument("-c", "--call", nargs="+", help="Call endpoint: <anchor> [method] [/path] [json_body]")
    url_parser.add_argument("anchor", nargs="?", help="Anchor name")
    url_parser.add_argument("method", nargs="?", help="HTTP method (GET, POST...)")
    url_parser.add_argument("route_path", nargs="?", help="Route path (e.g. /users)")
    url_parser.add_argument("kv", nargs="*", help="key=value pairs and optional status code")
    url_parser.add_argument("-F", "--files", action="store_true", help="Send files as multipart/form-data") 
    url_parser.set_defaults(func=url.run)




    # recreate (rc)
    rc_parser = subparsers.add_parser("rc", help="Restore environment from anchor files")
    rc_parser.add_argument("anchor", help="Anchor name to restore")
    rc_parser.add_argument("path", nargs="?", help="Target path to restore files into")
    rc_parser.set_defaults(func=rc.run)

    
    # cr
    cr_parser = subparsers.add_parser("cr", help="Create JSON structure from files/directories", description=load_help("cr"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    cr_parser.add_argument("name", help="Anchor name")
    cr_parser.add_argument("paths", nargs=argparse.REMAINDER, help="Paths with optional --mode and --blank flags")
    cr_parser.add_argument("--mode", help="Default mode if none is specified")
    cr_parser.set_defaults(func=handle_cr)

    

    # edit
    edit_parser = subparsers.add_parser("edit", help="Edit anchor or file (JSON/YAML)", description=load_help("edit"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    edit_parser.add_argument("name", help="Anchor name or path to JSON file")
    edit_parser.add_argument("--yml", action="store_true", help="Edit using YAML format")
    edit_parser.set_defaults(func=handle_edit)


    # ldap
    ldap_parser = subparsers.add_parser("ldap", help="LDAP operations", description=load_help("ldap"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    ldap_parser.add_argument("anchor", help="Anchor name (must be type 'ldap')")
    ldap_parser.add_argument("action", help="Action to perform (auth, export, import)")

    # Solo para auth
    ldap_parser.add_argument("username", nargs="?", help="LDAP username (used in auth)")
    ldap_parser.add_argument("password", nargs="?", help="LDAP password (used in auth)")

    # Comunes a export/import
    ldap_parser.add_argument("-f", "--filter", help="Raw LDAP filter (e.g. uid=manu)")
    ldap_parser.add_argument("--class", dest="cls", help="LDAP objectClass filter (e.g. inetOrgPerson)")

    # Export
    ldap_parser.add_argument("--ldif", help="Export result as LDIF to file")
    ldap_parser.add_argument("--json", nargs="?", const=True, help="Export result as JSON (optional path)")
    ldap_parser.add_argument("--csv", nargs="?", const=True, help="Export result as CSV")

    ldap_parser.add_argument("--add", action="store_true", help="Import LDIF entries with add operation")
    ldap_parser.add_argument("--modify", action="store_true", help="Import LDIF entries with modify operation")
    ldap_parser.add_argument("--delete", action="store_true", help="Import LDIF entries with delete operation")


    ldap_parser.set_defaults(func=ldap_cmd.run)



    # server
    server_parser = subparsers.add_parser("server", help="Interact with remote server", description=load_help("server"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    server_parser.add_argument("subcommand", choices=["auth", "ls", "url", "status"], help="Subcommand to run")
    server_parser.add_argument("-u", "--username", help="LDAP username")
    server_parser.add_argument("-p", "--password", help="LDAP password")
    server_parser.add_argument("value", nargs="?", help="Value for the subcommand (e.g., server URL)")
    server_parser.add_argument("-f", "--filter", help="Filter anchors on remote server (e.g. env=prod AND type=url)")
    server_parser.set_defaults(func=lambda args: server_cmd.run(args.subcommand, args))


    
    # push
    push_parser = subparsers.add_parser("push", help="Push anchor(s) to the server", description=load_help("push"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    push_parser.add_argument("name", nargs="?", default=None, help="Anchor name (optional if using --filter)")
    push_parser.add_argument("-f", "--filter", dest="filter_str", help="Filter anchors by metadata (e.g. env=prod)")
    push_parser.set_defaults(func=lambda args: push.push_command(args.name, args.filter_str))


    # pull
    pull_parser = subparsers.add_parser("pull", help="Download anchor(s) from the server", description=load_help("pull"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    pull_parser.add_argument("anchor", nargs="?", help="Anchor name (optional if using -f or --all)")
    pull_parser.add_argument("-f", "--filter", help="Metadata filter (e.g. env=prod)")
    pull_parser.add_argument("--all", action="store_true", help="Download all visible anchors")
    pull_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    pull_parser.set_defaults(func=lambda args: pull.run(args.anchor, args.filter, args.all, args.yes))

    

    # Sible (Ansible)
    sible_parser = subparsers.add_parser("sible", help="Execute ansible tasks defined in a template anchor", description=load_help("sible"), formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)
    sible_parser.add_argument("anchor", help="Anchor of type 'ansible' that defines the tasks to run")
    sible_parser.add_argument("host", nargs="?", help="One or more SSH anchors (comma-separated), or use -f to filter by metadata")
    sible_parser.add_argument("-f", "--filter", help="Metadata filter (e.g. env=prod AND project~web)")
    sible_parser.set_defaults(func=handle_sible)



    # secret
    secret_parser = subparsers.add_parser("secret", help="Manage encrypted secrets in remote", description=load_help("secret"),formatter_class=argparse.RawTextHelpFormatter, usage=argparse.SUPPRESS)

    secret_parser.add_argument(
        "subcommand",
        choices=["ls", "get", "pull", "update", "push", "del", "rm"],
        help="Subcommand to run"
    )
    secret_parser.add_argument("id", nargs="?", help="Secret ID")
    secret_parser.set_defaults(func=lambda args: secret.run(args.subcommand, args))






    args = parser.parse_args()

    # Rutas globales desde entorno
    args.anchor_dir = os.environ.get("ANCHOR_DIR", os.path.expanduser("~/.anchors/data"))
    args.env_dir = os.environ.get("ENV_DIR", args.anchor_dir)
    args.url_dir = os.environ.get("URL_DIR", args.anchor_dir)

    # Ejecutar el comando
    args.func(args)

if __name__ == "__main__":
    main()
