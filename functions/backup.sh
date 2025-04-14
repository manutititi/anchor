#!/usr/bin/env bash

anc_handle_backup() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local CYAN="\033[1;36m"
  local DIM="\033[2m"

  local backup_dir="$ANCHOR_HOME/backup"
  mkdir -p "$backup_dir"

  local anchors=()

  if [[ "$1" == "-f" || "$1" == "--filter" ]]; then
    shift
    mapfile -t anchors < <(filter_anchors "$1")
  elif [[ -n "$1" ]]; then
    anchors+=("$1")
  else
    echo -e "${YELLOW}Usage:${RESET} anc bck <anchor>  ${DIM}or${RESET}  anc bck -f key=value"
    return 1
  fi

  if [[ ${#anchors[@]} -eq 0 ]]; then
    echo -e "${YELLOW}⚠️ No matching anchors found${RESET}"
    return 1
  fi

  for name in "${anchors[@]}"; do
    local meta_file="$ANCHOR_DIR/$name.json"

    if [[ ! -f "$meta_file" ]]; then
      echo -e "${RED}⚠️ Anchor '$name' not found${RESET}"
      continue
    fi

    local path
    path=$(jq -r '.path // empty' "$meta_file")

    local anchor_backup_dir="$backup_dir/$name"
    mkdir -p "$anchor_backup_dir"

    # Guardar metadata
    cp "$meta_file" "$anchor_backup_dir/$name.json"

    # Verificar path y crear backup si es válido
    if [[ -z "$path" || ! -d "$path" ]]; then
      echo -e "${YELLOW}⚠️ Anchor '$name' has no valid local path. Skipping file backup.${RESET}"
      continue
    fi

    tar -czf "$anchor_backup_dir/files.tar.gz" -C "$path" . 2>/dev/null && \
      echo -e "${GREEN}✅ Backup completed for anchor '${BOLD}$name${RESET}${GREEN}'${RESET}" || \
      echo -e "${RED}❌ Failed to compress files for anchor '$name'${RESET}"
  done
}
