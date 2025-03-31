# anc — Anchor Management CLI

`anc` is a flexible, developer-first CLI to define, navigate, and manage directory anchors — bookmarks for local folders, remote paths, and project environments.

It’s a lightweight system that feels like a local shell extension, but scales into a cross-machine, metadata-aware, Git- and Docker-savvy workspace router.(docker and git under development, in the future ansible, tf)

---


<details>
<summary><strong>🚀 Installation</strong></summary>

### CLI Setup

Just run:

```bash
./install.sh
```


To enable anc server go to server folder and run docker compose
```bash
cd server
docker compose up --build -d
```

http://localhost:17017

</details>

### Why `anc`?

- **Jump instantly** to any directory, workspace, or remote path.
- **Tag and query** anchors by metadata like `env=dev`, `project=demo`, `type=remote`.
- **Copy, move, or run** commands across anchors with powerful filtering.
- **Understand your context**: auto-detects Git repos, Docker services, and notes.
- **Sync to a local server** to share or back up anchor metadata.
- **Evolve** toward a portable, smart router of environments for teams and infrastructure.

---

>  Built to grow from solo dev to team-level environment orchestration.
---

## Basic Navigation
```bash
anc
anc test
anc test ls
anc test tree
anc show test
```

- `anc` — Jump to the default anchor.
- `anc <name>` — Jump to a specific anchor.
- `anc <name> ls` — List contents of the anchor directory.
- `anc <name> tree` — Show tree view of the anchor.
- `anc show <name>` — Show metadata and path for an anchor.

---

## Anchor Management

```bash
anc set
anc set ./folder
anc set-ssh test ssh://user@host:/path
anc del test
anc rename old new
anc prune
anc note test "Project folder"
anc meta test env=dev project=demo
```

- `anc set` — Set anchor for current directory.
- `anc set ./folder` — Set anchor for a relative path.
- `anc set-ssh <name> <url>` — Set a remote SSH anchor.
- `anc del <name>` — Delete an anchor.
- `anc rename <old> <new>` — Rename an anchor.
- `anc prune` — Remove anchors pointing to non-existent paths.
- `anc note <name> [note]` — Add or update note.
- `anc meta <name> key=value ...` — Set metadata fields.

---

## File Transfer

```bash
anc cp file.txt test/
anc mv file.txt test/
anc cpt main/app.sh test/bin/
```

- `anc cp` — Copy file(s) to anchor (with optional subpath).
- `anc mv` — Move file(s) to anchor.
- `anc cpt` — Copy between anchors.

---

## Running Commands

```bash
anc run test make build
anc run -f env=dev "ls -la"
```

- `anc run <name> <cmd>` — Run command inside anchor directory.
- `anc run --filter key=value <cmd>` — Run command in anchors matching metadata.

---

## Server Sync

```bash
anc push test
anc pull test
anc pull --all
anc pull -f env=dev
anc server name [url]
anc server ls
anc server ls -f project=demo
anc server ls test
```

- `anc push <name>` — Upload anchor metadata to server.
- `anc pull <name>` — Download anchor metadata from server.
- `anc pull --all` — Pull all remote anchors.
- `anc pull -f key=value` — Pull anchors matching metadata.
- `anc server name [url]` — Set or show current server URL.
- `anc server ls` — List all anchors on the remote server.
- `anc server ls -f key=value` — Filter anchors by metadata.
- `anc server ls <name>` — Show full metadata for one anchor.

> **Tip:** You can combine multiple filters using `AND` / `OR`, like:
>
> ```bash
> anc server ls -f "env=dev AND project=demo"
> ```

---

## Web Dashboard

Access the web interface:

```
http://localhost:17017/dashboard
```
