#!/usr/bin/env bash
# TO DELETE

anc_show_anchor() {
  local anchor="$1"
  local meta_file="$ANCHOR_DIR/$anchor.json"

  if [[ -z "$anchor" ]]; then
    echo "Usage: anc show <anchor>"
    return 1
  fi

  if [[ ! -f "$meta_file" ]]; then
    echo "Anchor '$anchor' not found"
    return 1
  fi

  jq '.' "$meta_file"
}

