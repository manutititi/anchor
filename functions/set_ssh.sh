#!/usr/bin/env bash

anc_handle_set_ssh() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"
  local CYAN="\033[1;36m"

  local name="${1:-default}"
  local ssh_url="$2"

  if [[ -z "$ssh_url" || "$ssh_url" != ssh://* ]]; then
    echo -e "${YELLOW}Usage:${RESET} anc set-ssh <name> <ssh://user@host:/remote/path>${RESET}"
    return 1
  fi

  local full="${ssh_url#ssh://}"
  local user_host="${full%%:*}"
  local remote_path="${full#*:}"
  local user="${user_host%@*}"
  local host="${user_host#*@}"

  if [[ -z "$user" || -z "$host" || -z "$remote_path" ]]; then
    echo -e "${RED}❌ Invalid SSH path format${RESET}"
    return 1
  fi

  echo -e "${BLUE}🔌 Testing SSH connection to ${BOLD}$user_host${RESET}${BLUE}...${RESET}"

  if ssh "$user_host" "test -d '$remote_path'" 2>/dev/null; then
    local meta_file="$ANCHOR_DIR/$name"

    local remote_json
    remote_json=$(jq -n \
      --arg user "$user" \
      --arg host "$host" \
      --arg raw "$remote_path" \
      '{ user: $user, host: $host, raw_path: $raw }')

    jq -n \
      --arg path "ssh://$user_host:$remote_path" \
      --argjson remote "$remote_json" \
      '{ path: $path, type: "remote", remote: $remote }' > "$meta_file"

    echo -e "${CYAN}🌐 Remote anchor '${BOLD}$name${RESET}${CYAN}' set to: ${GREEN}$ssh_url${RESET}"
  else
    echo -e "${RED}❌ Could not connect or directory does not exist: $remote_path${RESET}"
    return 1
  fi
}


# TODO- Add git docker metadata
