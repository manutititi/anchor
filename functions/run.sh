#!/usr/bin/env bash

filter_anchors() {
  local query="$1"
  ANCHOR_DIR="$ANCHOR_DIR" python3 "$ANCHOR_ROOT/core/utils/filter.py" "$query"
}

anc_handle_run() {
  local anchor_dir="$ANCHOR_DIR"
  shift
  local filter_string=""
  local cmd=""
  local mode="single"
  local files=()

  if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
    filter_string="$2"
    shift 2
    cmd="$*"

    if [[ -z "$cmd" ]]; then
      echo -e "Usage: anc run -f key=value[,key=value...] <command>"
      return 1
    fi

    mapfile -t files < <(filter_anchors "$filter_string")
    mode="filtered"
  else
    local anchor="$1"
    shift
    cmd="$*"

    if [[ -z "$anchor" || -z "$cmd" ]]; then
      echo -e "Usage: anc run <anchor> <command>"
      return 1
    fi

    if [[ ! -f "$anchor_dir/$anchor.json" ]]; then
      echo -e "⚠️ Anchor '$anchor' not found"
      return 1
    fi

    files+=("$anchor")
  fi

  for name in "${files[@]}"; do
    local meta_file="$anchor_dir/$name.json"
    local path
    local raw_path
    raw_path=$(jq -r '.path // empty' "$meta_file")

    if [[ -z "$raw_path" ]]; then
      echo -e "⚠️ Anchor '$name' has no path, skipping"
      continue
    fi

    # Expandir rutas relativas y ~
    if [[ "$raw_path" == "~/"* ]]; then
      path="${HOME}/${raw_path:2}"
    elif [[ "$raw_path" == "./"* || "$raw_path" == "../"* ]]; then
      path="$(realpath "$ANCHOR_HOME/$raw_path" 2>/dev/null)"
    else
      path="$(realpath "$raw_path" 2>/dev/null)"
    fi

    echo -e "🔗 Running in '${name}' → ${path}:"

    if [[ "$raw_path" == ssh://* ]]; then
      if [[ "$raw_path" =~ ^ssh://([^:]+):(.+)$ ]]; then
        local user_host="${BASH_REMATCH[1]}"
        local remote_path="${BASH_REMATCH[2]}"
        ssh "$user_host" -t "cd '$remote_path' && $cmd"
      else
        echo -e "❌ Invalid SSH path format in anchor '$name': $raw_path"
      fi
    elif [[ -d "$path" ]]; then
      (cd "$path" && eval "$cmd")
    else
      echo -e "❌ Path '$path' is not valid or not a directory"
    fi
  done
}
