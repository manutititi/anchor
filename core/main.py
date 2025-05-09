#!/usr/bin/env python3
import argparse
import os
import sys

# Añadir ruta raíz al PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Importar subcomandos
from commands import ls, meta, url, rc
from commands import set as set_cmd
from core.commands import docker as docker_cmd
from commands import delete
from commands import ldap as ldap_cmd


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
    set_parser = subparsers.add_parser("set", help="Create or update an anchor")
    set_parser.add_argument("name", nargs="?", help="Anchor name or path")
    set_parser.add_argument("--url", action="store_true", help="Create a URL-type anchor")
    set_parser.add_argument("--env", action="store_true", help="Create an environment anchor")
    set_parser.add_argument("--ldap", action="store_true", help="Create an LDAP anchor")
    set_parser.add_argument("--docker", action="store_true", help="Create a Docker-type anchor")
    set_parser.add_argument("--rel", action="store_true", help="Store path relative to home (~)")
    set_parser.add_argument("--server", nargs="?", const="http://localhost:17017", help="Set server URL (default: localhost:17017)")
    set_parser.add_argument("base_url", nargs="?", help="Base URL or .env file depending on context")

        # Optionals LDAP
    set_parser.add_argument("--base-dn", help="Base DN for LDAP anchor")
    set_parser.add_argument("--bind-dn", help="Bind DN for LDAP admin")
    set_parser.add_argument("--bind-password", help="Bind password for LDAP")

    set_parser.set_defaults(func=set_cmd.run)


    # del
    del_parser = subparsers.add_parser("del", help="Delete anchors")
    del_parser.add_argument("name", nargs="?", help="Anchor name")
    del_parser.add_argument("-f", "--filter", help="Filter in key=value format")
    del_parser.set_defaults(func=delete.run)


    # meta
    meta_parser = subparsers.add_parser("meta", help="Update metadata")
    meta_parser.add_argument("-f", "--filter", help="Filter anchors")
    meta_parser.add_argument("args", nargs="*", help="Anchor name followed by key=value pairs")
    meta_parser.add_argument("--del", nargs="+", dest="delete", help="Keys to delete")
    meta_parser.set_defaults(func=meta.run)


    


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




    # restore (rc)
    rc_parser = subparsers.add_parser("rc", help="Restore environment from anchor files")
    rc_parser.add_argument("anchor", help="Anchor name to restore")
    rc_parser.add_argument("path", nargs="?", help="Target path to restore files into")
    rc_parser.set_defaults(func=rc.run)





    
    # docker
    docker_parser = subparsers.add_parser("docker", help="Manage docker-based anchors")
    docker_parser.add_argument("-r", "--restore", nargs="+", help="Restore a docker anchor into a directory")
    docker_parser.set_defaults(func=docker_cmd.run)




    # ldap
    ldap_parser = subparsers.add_parser("ldap", help="LDAP operations")
    ldap_parser.add_argument("anchor", help="Anchor name (must be type 'ldap')")
    ldap_parser.add_argument("action", help="Action to perform (auth, get-user, etc.)")
    ldap_parser.add_argument("username", nargs="?", help="LDAP username")
    ldap_parser.add_argument("password", nargs="?", help="LDAP password")
    ldap_parser.add_argument("--json", action="store_true", help="Output result in JSON format")
    ldap_parser.add_argument("--class", dest="cls", help="LDAP objectClass to filter (e.g. inetOrgPerson)")
    ldap_parser.set_defaults(func=ldap_cmd.run)




    args = parser.parse_args()

    # Rutas globales desde entorno
    args.anchor_dir = os.environ.get("ANCHOR_DIR", os.path.expanduser("~/.anchors/data"))
    args.env_dir = os.environ.get("ENV_DIR", args.anchor_dir)
    args.url_dir = os.environ.get("URL_DIR", args.anchor_dir)

    # Ejecutar el comando
    args.func(args)

if __name__ == "__main__":
    main()
