#!/usr/bin/env bash

source "${BASH_SOURCE%/*}/generate_metadata.sh"

anc_handle_set() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local GREEN="\033[0;32m"
  local CYAN="\033[1;36m"
  local BLUE="\033[1;34m"
  local RED="\033[0;31m"
  local YELLOW="\033[0;33m"

  local name="${1:-default}"
  local path="$(pwd)"
  local meta_file="$ANCHOR_DIR/$name"

  local meta_json
  anc_generate_metadata "$path" meta_json

  # Establecer rama fija .git.set_branch = .git.branch si está presente
  meta_json=$(jq '.git.set_branch = .git.branch' <<< "$meta_json")

  echo "$meta_json" > "$meta_file"

  echo -e "${CYAN}⚓ Anchor '${BOLD}$name${RESET}${CYAN}' set to: ${GREEN}$path${RESET}"

  # Mostrar detalles si tiene Git
  if jq -e '.git.root // empty' <<< "$meta_json" >/dev/null; then
    local git_branch
    git_branch=$(jq -r '.git.branch' <<< "$meta_json")
    local git_root
    git_root=$(jq -r '.git.root' <<< "$meta_json")
    local git_msg
    git_msg=$(jq -r '.git.commit.message // empty' <<< "$meta_json")
    local is_dirty
    is_dirty=$(jq -r '.git.is_dirty // false' <<< "$meta_json")

    echo -e "${BLUE}🔍 Git repository detected:${RESET}"
    echo -e "  ${CYAN}Branch:${RESET} $git_branch"
    echo -e "  ${CYAN}Root:${RESET} $git_root"
    echo -e "  ${CYAN}Last commit:${RESET} $git_msg"
    [[ "$is_dirty" == "true" ]] && echo -e "  ${RED}⚠️ Working directory has uncommitted changes${RESET}"
  fi

  # Mostrar detalles si tiene Docker
  if jq -e '.docker.active // false' <<< "$meta_json" >/dev/null; then
    local services
    services=$(jq -r '.docker.services[]?.name' <<< "$meta_json")
    echo -e "${BLUE}🐳 Docker Compose detected:${RESET}"
    echo -e "  ${CYAN}Services:${RESET}"
    for s in $services; do
      echo -e "    - $s"
    done
  fi
}

