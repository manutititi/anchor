#!/usr/bin/env bash

anc_handle_prune() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local CYAN="\033[1;36m"
  local DIM="\033[2m"
  local BLUE="\033[1;34m"

  local anchor_dir="$ANCHOR_DIR"
  echo -e "${YELLOW}🧹 Scanning for dead local anchors (type=local)...${RESET}"
  local dead=()

  for file in "$anchor_dir"/*; do
    [[ -f "$file" ]] || continue
    local name
    name="$(basename "$file")"

    local type
    type=$(jq -r '.type // "local"' "$file")

    [[ "$type" != "local" ]] && continue

    local path
    path=$(jq -r '.path // empty' "$file")

    [[ -d "$path" ]] || dead+=("$name")
  done

  if [[ ${#dead[@]} -eq 0 ]]; then
    echo -e "${GREEN}✅ No dead local anchors found${RESET}"
    return 0
  fi

  echo -e "${RED}⚠️ The following local anchors point to non-existent directories:${RESET}"
  for name in "${dead[@]}"; do
    local path
    path=$(jq -r '.path' "$anchor_dir/$name")
    echo -e "  ${CYAN}⚓ $name${RESET} → ${DIM}$path${RESET}"
  done

  echo -ne "${YELLOW}❓ Remove these anchors? (y/N): ${RESET}"
  read -r confirm

  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo -e "${BLUE}❌ Operation cancelled${RESET}"
    return 0
  fi

  for name in "${dead[@]}"; do
    rm "$anchor_dir/$name"
    echo -e "${RED}🗑️ Anchor '${BOLD}$name${RESET}${RED}' deleted${RESET}"
  done
}

