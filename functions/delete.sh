#!/usr/bin/env bash

anc_handle_del() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local CYAN="\033[1;36m"
  local BLUE="\033[1;34m"
  local DIM="\033[2m"

  local anchor_dir="$ANCHOR_DIR"
  shift
  local files=()

  if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
    local filter_string="$2"
    shift 2
    mapfile -t files < <(filter_anchors "$filter_string")
  elif [[ -n "$1" ]]; then
    files+=("$1")
  else
    echo -e "${YELLOW}Usage:${RESET} anc del <name>  ${DIM}or${RESET}  anc del -f key=value[,key=value...]"
    return 1
  fi

  if [[ ${#files[@]} -eq 0 ]]; then
    echo -e "${YELLOW}⚠️ No matching anchors found${RESET}"
    return 1
  fi

  echo -e "${RED}🚨 The following anchors will be deleted:${RESET}"
  for name in "${files[@]}"; do
    echo -e "  ${CYAN}⚓ $name${RESET}"
  done

  echo -ne "${YELLOW}❓ Are you sure? (y/N): ${RESET}"
  read -r confirm

  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo -e "${BLUE}❌ Operation cancelled${RESET}"
    return 0
  fi

  for name in "${files[@]}"; do
    local meta_file="$anchor_dir/$name"
    if [[ -f "$meta_file" ]]; then
      rm "$meta_file"
      echo -e "${RED}🗑️ Anchor '${BOLD}$name${RESET}${RED}' deleted${RESET}"
    else
      echo -e "${YELLOW}⚠️ Anchor '$name' not found${RESET}"
    fi
  done
}

