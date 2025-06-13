#!/usr/bin/env bash

filter_anchors() {
  local query="$1"
  ANCHOR_DIR="$ANCHOR_DIR" python3 "$ANCHOR_ROOT/core/utils/filter.py" "$query"
}

resolve_path_from_anchor() {
  local raw_path="$1"

  # Expandir ~, ./ y ../ correctamente
  if [[ "$raw_path" == "~/"* ]]; then
    echo "${HOME}/${raw_path:2}"
  elif [[ "$raw_path" == "./"* || "$raw_path" == "../"* ]]; then
    realpath "$ANCHOR_HOME/$raw_path" 2>/dev/null
  else
    realpath "$raw_path" 2>/dev/null
  fi
}

anc_handle_run() {
  local anchor_dir="$ANCHOR_DIR"
  shift
  local filter_string=""
  local cmd=""
  local files=()

  # Modo con filtro
  if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
    filter_string="$2"
    shift 2
    cmd="$*"

    if [[ -z "$cmd" ]]; then
      echo -e "${YELLOW}Usage:${RESET} anc run -f key=value[,key=value] <command>"
      return 1
    fi

    mapfile -t files < <(filter_anchors "$filter_string")
  else
    # Modo normal: anchor directo
    local anchor="$1"
    shift
    cmd="$*"

    if [[ -z "$anchor" || -z "$cmd" ]]; then
      echo -e "${YELLOW}Usage:${RESET} anc run <anchor> <command>${RESET}"
      return 1
    fi

    if [[ ! -f "$anchor_dir/$anchor.json" ]]; then
      echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
      return 1
    fi

    files+=("$anchor")
  fi

  # Advertencia si el comando incluye comodines sin comillas
  if [[ "$cmd" == *"*"* && "$cmd" != *\"* && "$cmd" != *\'* ]]; then
    echo -e "${YELLOW}⚠️ Hint:${RESET} If using wildcards, quote your command: anc run <anchor> \"rm -rf *\""
  fi

  for name in "${files[@]}"; do
    local meta_file="$anchor_dir/$name.json"
    local raw_path=$(jq -r '
      if has("path") then .path
      elif (.paths | type == "array") then
        (.paths[] | select(.default == true).path) // .paths[0].path
      else empty end
    ' "$meta_file")

    if [[ -z "$raw_path" ]]; then
      echo -e "${RED}⚠️ Anchor '$name' has no usable path, skipping${RESET}"
      continue
    fi

    local path
    path=$(resolve_path_from_anchor "$raw_path")

    echo -e "${BLUE}🔗 Running in '${name}' → ${path}:${RESET}"

    if [[ "$raw_path" == ssh://* ]]; then
      if [[ "$raw_path" =~ ^ssh://([^@]+)@([^:/]+):(.+)$ ]]; then
        local user="${BASH_REMATCH[1]}"
        local host="${BASH_REMATCH[2]}"
        local remote_path="${BASH_REMATCH[3]}"
        ssh "$user@$host" -t "cd '$remote_path' && $cmd"
      else
        echo -e "${RED}❌ Invalid SSH path format in anchor '$name': $raw_path${RESET}"
      fi
    elif [[ "$path" == /* && -d "$path" ]]; then
      (cd "$path" && eval "$cmd")
    else
      echo -e "${RED}❌ Path '$path' is not valid or not a directory${RESET}"
    fi
  done
}
