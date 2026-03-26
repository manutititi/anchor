#!/usr/bin/env bash
# TO DELETE

anc_handle_edit() {
  local name="$1"
  local file="$ANCHOR_DIR/$name.json"

  if [[ -z "$name" ]]; then
    echo "Usage: anc edit <name>"
    return 1
  fi

  if [[ ! -f "$file" ]]; then
    echo "❌ Anchor '$name' not found."
    return 1
  fi

  ${EDITOR:-nano} "$file"
}
