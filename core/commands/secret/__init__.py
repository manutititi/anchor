from . import ls, get, pull, update, push

def run(action, args):
    if action == "ls":
        return ls.run(args)
    elif action == "get":
        return get.run(args)
    elif action == "pull":
        return pull.run(args)
    elif action == "update":
        return update.run(args)
    elif action == "push":
        return push.run(args)
    else:
        print(f"❌ Unknown ref command: {action}")
