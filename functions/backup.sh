#!/usr/bin/env bash

filter_anchors() {
  local query="$1"
  ANCHOR_DIR="${ANCHOR_DIR:-$ANCHOR_ROOT/data}" python3 "$ANCHOR_ROOT/core/utils/filter.py" "$query"
}

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

  # --- MODO RESTORE ---
  if [[ "$1" == "-r" || "$1" == "--restore" ]]; then
    shift
    local name="$1"
    local anchor_backup_dir="$backup_dir/$name"

    if [[ -z "$name" ]]; then
      echo -e "${YELLOW}Usage:${RESET} anc bck -r <anchor>"
      return 1
    fi

    if [[ ! -d "$anchor_backup_dir" ]]; then
      echo -e "${RED}❌ No backup found for anchor '$name' at $anchor_backup_dir${RESET}"
      return 1
    fi

    local meta_file_src="$anchor_backup_dir/$name.json"
    if [[ ! -f "$meta_file_src" ]]; then
      echo -e "${RED}❌ Metadata file not found: $meta_file_src${RESET}"
      return 1
    fi

    local meta_file_dst="$ANCHOR_DIR/$name.json"
    cp "$meta_file_src" "$meta_file_dst"
    echo -e "${GREEN}✅ Metadata restored to $meta_file_dst${RESET}"

    local path
    path=$(jq -r '.path // empty' "$meta_file_dst")

    if [[ -z "$path" ]]; then
      echo -e "${YELLOW}⚠️ No 'path' defined in metadata. Skipping file restore.${RESET}"
      return 0
    fi

    local files_archive="$anchor_backup_dir/files.tar.gz"
    if [[ -f "$files_archive" ]]; then
      if [[ -d "$path" && "$(ls -A "$path" 2>/dev/null)" ]]; then
        echo -ne "${YELLOW}⚠️ Directory '$path' already exists and is not empty. Overwrite? [y/N] ${RESET}"
        read -r confirm
        [[ "$confirm" != "y" && "$confirm" != "Y" ]] && {
          echo -e "${DIM}⏭️ Skipped restoring files for '$name'${RESET}"
          return 0
        }
      fi
      mkdir -p "$path"
      tar -xzf "$files_archive" -C "$path"
      echo -e "${GREEN}📦 Files restored to '$path'${RESET}"
    else
      echo -e "${YELLOW}⚠️ No file archive found for '$name'. Only metadata was restored.${RESET}"
    fi
    return
  fi

  # --- MODO BACKUP ---
  local anchors=()

  if [[ "$1" == "--all" ]]; then
    shift
    mapfile -t anchors < <(find "$ANCHOR_DIR" -name "*.json" -exec basename {} .json \;)
    if [[ "$1" == "-f" || "$1" == "--filter" ]]; then
      shift
      mapfile -t anchors < <(printf "%s\n" "${anchors[@]}" | filter_anchors "$1")
    fi
  elif [[ "$1" == "-f" || "$1" == "--filter" ]]; then
    shift
    mapfile -t anchors < <(filter_anchors "$1")
  elif [[ -n "$1" ]]; then
    anchors+=("$1")
  else
    echo -e "${YELLOW}Usage:${RESET} anc bck <anchor>  ${DIM}or${RESET}  anc bck -f key=value  ${DIM}or${RESET}  anc bck --all  ${DIM}or${RESET}  anc bck -r <anchor>"
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

    local raw_path
    raw_path=$(jq -r '.path // empty' "$meta_file")

    local path=""
    if [[ -n "$raw_path" ]]; then
      if [[ "$raw_path" == "~/"* ]]; then
        raw_path="${HOME}/${raw_path:2}"
      elif [[ "$raw_path" == "./"* || "$raw_path" == "../"* ]]; then
        raw_path="$ANCHOR_HOME/$raw_path"
      fi
      path=$(realpath "$raw_path" 2>/dev/null || echo "")
    fi

    local anchor_backup_dir="$backup_dir/$name"
    mkdir -p "$anchor_backup_dir"

    cp "$meta_file" "$anchor_backup_dir/$name.json"
    echo "$raw_path" > "$anchor_backup_dir/path_original.txt"
    date '+%Y-%m-%d %H:%M:%S' > "$anchor_backup_dir/backup_date.txt"

    if [[ -z "$path" || ! -d "$path" ]]; then
      echo -e "${YELLOW}⚠️ Anchor '$name' has no valid local path. Skipping file backup.${RESET}"
      continue
    fi

    tar -czf "$anchor_backup_dir/files.tar.gz" -C "$path" . 2>/dev/null && \
      echo -e "${GREEN}✅ Backup completed for anchor '${BOLD}$name${RESET}${GREEN}'${RESET}" || \
      echo -e "${RED}❌ Failed to compress files for anchor '$name'${RESET}"
  done
}
