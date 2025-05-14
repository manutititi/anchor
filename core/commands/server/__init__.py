from . import auth, ls

def run(action, args):
    if action == "auth":
        return auth.run(args)
    elif action == "ls":
        return ls.run(args)
    else:
        print(f"❌ Unknown server command: {action}")
