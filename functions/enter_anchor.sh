#!/usr/bin/env bash

source "${BASH_SOURCE%/*}/generate_metadata.sh"
source "${BASH_SOURCE%/*}/env.sh"

anc_enter_anchor() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"
  local CYAN="\033[1;36m"
  local DIM="\033[2m"

  local name="$1"
  local second_arg="$2"
  local meta_file="$ANCHOR_DIR/$name.json"

  if [[ ! -f "$meta_file" ]]; then
    echo -e "${RED}⚠️ Anchor '$name' not found${RESET}"
    return 1
  fi

  local type
  type=$(jq -r '.type // "local"' "$meta_file")

  # 🌐 Abrir URL si es tipo url
  if [[ "$type" == "url" ]]; then
    local base_url
    base_url=$(jq -r '.endpoint.base_url // empty' "$meta_file")
    if [[ -n "$base_url" ]]; then
      echo -e "${BLUE}🌐 Opening URL anchor '$name' → $base_url${RESET}"
      xdg-open "$base_url" >/dev/null 2>&1 &
    else
      echo -e "${RED}❌ URL anchor '$name' has no base_url${RESET}"
    fi
    return
  fi

  # 📡 Conexión SSH moderna (type = ssh)
  if [[ "$type" == "ssh" ]]; then
    local user host remote_path
    user=$(jq -r '.ssh.user // empty' "$meta_file")
    host=$(jq -r '.ssh.host // empty' "$meta_file")
    remote_path=$(jq -r '.ssh.path // empty' "$meta_file")

    if [[ -z "$user" || -z "$host" || -z "$remote_path" ]]; then
      echo -e "${RED}❌ Invalid SSH anchor: missing user, host or path${RESET}"
      return 1
    fi

    echo -e "${BLUE}🔐 Connecting to SSH anchor '${BOLD}$user@$host${RESET}${BLUE}' → ${GREEN}$remote_path${RESET}"
    ssh "$user@$host" -t "cd '$remote_path' && exec bash"
    return $?
  fi

  # Aplicar entorno si es tipo env
  if [[ "$type" == "env" ]]; then
    echo -e "${CYAN}🧪 Detected environment anchor '${BOLD}$name${RESET}${CYAN}', applying...${RESET}"
    anc_env_apply "$name" --no-link
    return $?
  fi

  # Leer path
  local raw_path
  raw_path=$(jq -r '.path // empty' "$meta_file")
  local path="$raw_path"
  if [[ "$path" == "~/"* ]]; then
    path="${HOME}${path:1}"
  fi

  if [[ -z "$path" ]]; then
    echo -e "${RED}❌ No 'path' found in anchor '${BOLD}$name${RESET}${RED}'${RESET}"
    return 1
  fi

  # 🔄 Generar metadata y restaurar path original
  local current_json
  anc_generate_metadata "$path" current_json
  current_json=$(jq --arg p "$raw_path" '.path = $p' <<< "$current_json")

  if jq -e '.git.set_branch' "$meta_file" >/dev/null; then
    local fixed_branch
    fixed_branch=$(jq -r '.git.set_branch' "$meta_file")
    current_json=$(jq --arg b "$fixed_branch" '.git.set_branch = $b' <<< "$current_json")
  fi

  if [[ "$(jq -S . <<< "$current_json")" != "$(jq -S . "$meta_file")" ]]; then
    echo "$current_json" > "$meta_file"
  fi

  # 📡 Soporte heredado para ssh://
  if [[ "$path" =~ ^ssh://([a-zA-Z0-9._%-]+@[a-zA-Z0-9._%-]+):(.+) ]]; then
    local user_host="${BASH_REMATCH[1]}"
    local remote_path="${BASH_REMATCH[2]}"
    echo -e "${BLUE}🔐 Connecting to remote anchor: ${BOLD}$user_host${RESET}${BLUE} at ${GREEN}$remote_path${RESET}"
    ssh "$user_host" -t "cd '$remote_path' && exec bash"
    return $?
  fi

  # 📁 Anchor local
  if [[ ! -d "$path" ]]; then
    echo -e "${RED}❌ Anchor '$name' points to non-existent directory: $path${RESET}"
    return 1
  fi

  case "$second_arg" in
    ls)
      echo -e "${BLUE}📂 Listing contents of '${BOLD}$name${RESET}${BLUE}' ($path):${RESET}"
      ls -la "$path"
      ;;
    tree)
      echo -e "${BLUE}🌲 Tree view of '${BOLD}$name${RESET}${BLUE}' ($path):${RESET}"
      if command -v tree >/dev/null 2>&1; then
        tree "$path"
      else
        echo -e "${YELLOW}⚠️ 'tree' command not found. Please install it first.${RESET}"
      fi
      ;;
    *)
      cd "$path" || {
        echo -e "${RED}❌ Failed to access anchor '$name'${RESET}"
        return 1
      }

      if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local anchor_branch
        anchor_branch=$(jq -r '.git.set_branch // empty' <<< "$current_json")

        if [[ -n "$anchor_branch" ]]; then
          local current_branch
          current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

          if [[ "$current_branch" != "$anchor_branch" ]]; then
            if git show-ref --verify --quiet "refs/heads/$anchor_branch"; then
              git switch "$anchor_branch" >/dev/null 2>&1
            fi
          fi
        fi
      fi
      ;;
  esac
}
