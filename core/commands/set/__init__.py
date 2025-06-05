# core/commands/set/__init__.py

from core.commands.set import env, url, ldap, local, server, ssh, ansible, workflow

def run(args):
    if args.server:
        return server.run(args)
    if args.env:
        return env.run(args)
    if args.url:
        return url.run(args)
    if args.ldap:
        return ldap.run(args)
    elif args.ssh:
        return ssh.run(args)
    elif args.ansible:
        return ansible.run(args)
    elif args.workflow:
        return workflow.run(args)
    
    return local.run(args)
