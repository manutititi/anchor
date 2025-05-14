from . import auth, ls, url

def run(action, args):
    if action == "auth":
        return auth.run(args)
    elif action == "ls":
        return ls.run(args)
    elif action == "url":
        return url.run(args)
    else:
        print(f"❌ Unknown server command: {action}")
