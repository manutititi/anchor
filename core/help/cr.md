# anc cr

Create a structured JSON representation of files and directories for later recreation.

## USAGE

```
anc cr <name> <path> [--mode <mode>] [--blank] <path> [--mode <mode>] ...
```

## OPTIONS

- `--mode <value>`  
  Mode to apply to the previous path:
  - `replace`: Replace full content (default)
  - `append`: Add content to the end of file
  - `prepend`: Add content at the beginning
  - `regex`: Match lines using regex and apply submode

- `--blank`  
  Apply to the previous path: store empty content only

## EXAMPLES

```
# Save a directory with default mode (replace)
anc cr myenv ~/project/config

# Save different paths with individual modes
anc cr conf /etc/sysctl.conf --mode regex ~/.bashrc --mode append

# Save a directory without content
anc cr skeleton env/ --blank

# Combine multiple options
anc cr multi docker-compose.yml --blank scripts/start.sh --mode prepend /etc/sysctl.conf --mode regex

# Then edit the anchor JSON to add a regex:
#   "regex": "^net\\.ipv4\\.ip_forward\\s*=.*",
#   "content": "net.ipv4.ip_forward = 1"
```

## NOTES

- Each `--mode` and `--blank` applies to the path that appears **before** it.
- If `--mode regex` is used, `"regex"` and `"submode"` are initialized, and `"content"` is left empty by default.
- Anchors are stored in `$ANCHOR_DIR` (default: `./data`) as JSON.
- To restore the files later, use: