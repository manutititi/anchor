# anc — Anchor Management CLI

`anc` is a modular CLI and optional server for managing paths, scripts, files, secrets, environments, and infrastructure workflows through **anchors** — executable, metadata-rich JSON objects.

Built for DevOps teams and developers, `anc` evolves from a shell utility to a portable automation framework: syncable, declarative, and extensible.

---

<details>
<summary><strong>🚀 Installation</strong></summary>

### CLI Setup

```bash
./install.sh
```

### Launch the Server (optional)

```bash
cd server
docker compose up --build -d
```

- Dashboard: http://localhost:17017/dashboard  
- API: http://localhost:17017
</details>

---

## 🔑 Key Concepts

- **Anchors**: JSON-based units representing paths, environments, secrets, tasks, or workflows.
- **Types**: `local`, `ssh`, `url`, `env`, `files`, `ansible`, `secret`.
- **Filtering**: Query anchors by metadata using expressions like `env=prod AND project=web`.
- **Modular**: Each command is composable, scriptable, and server-aware.

---

## 📁 Anchor Management

```bash
anc set                # Set anchor for current directory
anc set --ssh name user@host:/path -i /path/to/key
anc set --url name https://example.com
anc set --env name .env
anc set --ansible name
anc show name
anc ls
anc ls -f project=web
anc note name "Optional comment"
anc meta name env=dev project=demo
anc rename old new
anc del name
anc prune              # Remove anchors with invalid paths
```

---

## 🔄 File Operations

```bash
anc cp file.txt anchor/
```

---

## 🧨 Command Execution

```bash
anc run dev "npm install"
anc run -f env=prod "systemctl restart nginx"
```

---

## 🌐 Server Sync

```bash
anc server auth                      # Authenticate via LDAP
anc server name https://host:17017  # Set server URL
anc server ls                       # List remote anchors
anc server ls -f env=prod
anc server show name

anc push name                       # Upload anchor to server
anc pull name                       # Download anchor from server
anc pull --all
anc pull -f project=infra
```

Filters support advanced logic:

```bash
anc server ls -f "env=prod AND project~web"
```

---

## 🔐 Secret Management

```bash
anc secret push name [.env]         # Encrypt and push secret
anc secret get name                 # Decrypt and show
anc secret update name              # Interactive update
anc secret del name                 # Delete secret
```

Supports interactive and non-interactive modes with `--desc`, `--groups`, `--users`, `--secret`, and `--json`.

Secrets are stored encrypted (AES-GCM), and access is controlled by group/user policies via LDAP.

---

## 🔁 Environment Snapshots

```bash
anc cr name                         # Capture current folder as files anchor
anc cr name /path/to/1 path/to/2    # Capture current folder as files anchor
anc rc name                         # Restore to current directory
```

---

## ⚙️ Workflows

```bash
anc wf myflow
```

Run declarative workflows combining:

- `anc`: internal commands
- `shell`: system commands
- `files`: restore anchors
- `api`: HTTP requests
- `sleep`, `watch`, `set`, etc.


Workflows support loops, variables, secrets, and conditionals.

---

## 📊 Web Dashboard

Access via:

```
http://localhost:17017/dashboard
```
Still in development

---

## 🧠 Philosophy

`anc` treats configuration, environments, and actions as executable knowledge.  
Every anchor is portable, inspectable, and composable — designed to work locally, remotely, or across teams.

> From personal workspace shortcuts to distributed automation workflows.

---

