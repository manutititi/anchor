from commands.ldap import auth, export


def run(args):
    if args.action == "auth":
        from . import auth
        return auth.run(args)
    if args.action == "users":
        from . import users
        return users.run(args)
    if args.action == "groups":
        from . import groups
        return groups.run(args)
    if args.action == "export":
        from . import export
        return export.run(args)

    print(f"❌ Unknown ldap action: {args.action}")
