#!/usr/bin/env bash

anc_handle_run() {
  local anchor_dir="$ANCHOR_DIR"
  shift
  local filter_string=""
  local mode="single"
  local cmd=""
  local files=()

  if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
    filter_string="$2"
    shift 2
    cmd="$*"

    if [[ -z "$cmd" ]]; then
      echo -e "${YELLOW}Usage:${RESET} anc run -f key=value[,key=value...] <command>"
      return 1
    fi

    mapfile -t files < <(filter_anchors "$filter_string")
    mode="filtered"
  else
    local anchor="$1"
    shift
    cmd="$*"

    if [[ -z "$anchor" || -z "$cmd" ]]; then
      echo -e "${YELLOW}Usage:${RESET} anc run <anchor> <command>"
      return 1
    fi

    if [[ ! -f "$anchor_dir/$anchor" ]]; then
      echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
      return 1
    fi

    files+=("$anchor")
  fi

  for name in "${files[@]}"; do
    local meta_file="$anchor_dir/$name"
    local path
    path=$(jq -r '.path // empty' "$meta_file")

    if [[ -z "$path" ]]; then
      echo -e "${YELLOW}⚠️ Anchor '$name' has no path, skipping${RESET}"
      continue
    fi

    echo -e "${CYAN}⚓ Running in '$name' → $path:${RESET}"

    if [[ "$path" == ssh://* ]]; then
      if [[ "$path" =~ ^ssh://([^:]+):(.+)$ ]]; then
        local user_host="${BASH_REMATCH[1]}"
        local remote_path="${BASH_REMATCH[2]}"
        ssh "$user_host" -t "cd '$remote_path' && $cmd"
      else
        echo -e "${RED}❌ Invalid SSH path format in anchor '$name': $path${RESET}"
        continue
      fi
    else
      (cd "$path" && eval "$cmd")
    fi
  done
}

