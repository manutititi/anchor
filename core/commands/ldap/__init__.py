from commands.ldap import auth, users, groups, export

def run(args):
    if args.action == "auth":
        return auth.run(args)
    if args.action == "users":
        return users.run(args)
    if args.action == "groups":
        return groups.run(args)
    if args.action == "export":
        return export.run(args)

    print("Unknown ldap action")
