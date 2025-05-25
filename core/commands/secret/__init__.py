from . import ls, get, pull, update, push, del_cmd

def run(subcommand, args):
    if subcommand == "ls":
        return ls.run(args)
    elif subcommand == "get":
        return get.run(args)
    elif subcommand == "pull":
        return pull.run(args)
    elif subcommand == "update":
        return update.run(args)
    elif subcommand == "push":
        return push.run(args)
    elif subcommand in ("del", "rm"):
        return del_cmd.run(args)
    else:
        print(f"❌ Unknown secret command: {subcommand}")
