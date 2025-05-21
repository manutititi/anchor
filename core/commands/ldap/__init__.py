from commands.ldap import auth, export, ldap_import

def run(args):
    if args.action == "auth":
        return auth.run(args)
    if args.action == "export":
        return export.run(args)
    if args.action == "import":
        return ldap_import.run(args)

    print(f"❌ Unknown ldap action: {args.action}")
    return 1
