#!/usr/bin/env python3
import argparse
import os
import sys

# Agregar la ruta raíz del proyecto al PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Importar subcomandos
from commands import ls
# from commands import meta  # ← lo activás cuando lo migramos

def main():
    parser = argparse.ArgumentParser(prog="anc", description="Anchor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comando: ls
    ls_parser = subparsers.add_parser("ls", help="List anchors")
    ls_parser.add_argument("-f", "--filter", help="Filter in key=value format")
    ls_parser.add_argument("-u", "--url", action="store_true", help="List from urls/")
    ls_parser.add_argument("-e", "--env", action="store_true", help="List from envs/")
    ls_parser.set_defaults(func=ls.run)

    # Aquí agregás más comandos al registrar sus funciones:
    # meta_parser = subparsers.add_parser("meta", help="Update metadata")
    # meta_parser.add_argument("anchor")
    # meta_parser.add_argument("kv_pairs", nargs="+")
    # meta_parser.set_defaults(func=meta.run)

    args = parser.parse_args()

    # Rutas definidas por entorno (bash las define en anchors.sh)
    args.anchor_dir = os.environ.get("ANCHOR_DIR", "data")
    args.env_dir = os.environ.get("ENV_DIR", "envs")
    args.url_dir = os.environ.get("URL_DIR", "urls")

    # Ejecutar la función asociada al subcomando
    args.func(args)

if __name__ == "__main__":
    main()
