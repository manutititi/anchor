#!/usr/bin/env python3
import argparse
import os
import sys

# Añadir ruta raíz al PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importar subcomandos
from commands import ls
from commands import set as set_cmd
from commands import delete

def main():
    parser = argparse.ArgumentParser(prog="anc", description="Anchor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comando: ls
    ls_parser = subparsers.add_parser("ls", help="List anchors")
    ls_parser.add_argument("-f", "--filter", help="Filter in key=value format")
    ls_parser.add_argument("-u", "--url", action="store_true", help="List anchors of type 'url'")
    ls_parser.add_argument("-e", "--env", action="store_true", help="List anchors of type 'env'")
    ls_parser.set_defaults(func=ls.run)

    # Comando: set
    set_parser = subparsers.add_parser("set", help="Create or update an anchor")
    set_parser.add_argument("name", nargs="?", help="Anchor name or path")
    set_parser.add_argument("--url", action="store_true", help="Create a URL-type anchor")
    set_parser.add_argument("--env", action="store_true", help="Create an environment anchor")
    set_parser.add_argument("base_url", nargs="?", help="Base URL or .env file depending on context")
    set_parser.add_argument("--rel", action="store_true", help="Store path relative to home (~)")
    set_parser.set_defaults(func=set_cmd.run)

    # Comando: del
    del_parser = subparsers.add_parser("del", help="Delete anchors")
    del_parser.add_argument("name", nargs="?", help="Anchor name")
    del_parser.add_argument("-f", "--filter", help="Filter in key=value format")
    del_parser.set_defaults(func=delete.run)

    args = parser.parse_args()

    # Rutas globales desde entorno
    args.anchor_dir = os.environ.get("ANCHOR_DIR", os.path.expanduser("~/.anchors/data"))
    args.env_dir = os.environ.get("ENV_DIR", args.anchor_dir)
    args.url_dir = os.environ.get("URL_DIR", args.anchor_dir)

    # Ejecutar el comando
    args.func(args)

if __name__ == "__main__":
    main()
