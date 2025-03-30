#!/usr/bin/env bash

anc_handle_help() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local CYAN="\033[1;36m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"

  echo -e "${BOLD}📖 anc - Simple anchor system for directories and files${RESET}\n"

  echo -e "${CYAN}🎯 Navigation:${RESET}"
  echo -e "  anc                        - ⚓ Go to the 'default' anchor"
  echo -e "  anc <name>                - ⚓ Jump to a specific anchor"
  echo -e "  anc <name> ls             - 📂 List contents of anchor directory"
  echo -e "  anc <name> tree           - 🌲 Tree view of anchor directory"
  echo -e "  anc show <name>           - 🔍 Show path, note, and metadata"
  echo -e "  anc ls [--filter k=v]     - 📌 List all anchors (optionally filtered by metadata)"
  echo

  echo -e "${CYAN}🛠️  Anchor Management:${RESET}"
  echo -e "  anc set [name]            - 📍 Set anchor for current directory"
  echo -e "  anc set-ssh <name> <url>  - 🌐 Set anchor to remote SSH path"
  echo -e "  anc del <name>            - 🗑️ Delete an anchor"
  echo -e "  anc rename <old> <new>    - 🔄 Rename an anchor"
  echo -e "  anc prune                 - 🧹 Remove anchors pointing to non-existent dirs"
  echo -e "  anc note <name> [msg]     - 📝 Add or update note for an anchor"
  echo -e "  anc meta <name> k=v ...   - 🧩 Set metadata (key=value) for an anchor"
  echo

  echo -e "${CYAN}📂 File Transfer:${RESET}"
  echo -e "  anc cp <file...> <anchor[/subpath]> - 📥 Copy one or more files/dirs to anchor"
  echo -e "  anc mv <file...> <anchor[/subpath]> - 🚚 Move one or more files/dirs to anchor"
  echo -e "  anc cpt <from-anchor[/path]> <to-anchor[/path]> - 🔁 Copy between anchors"
  echo

  echo -e "${CYAN}▶️  Execute Commands:${RESET}"
  echo -e "  anc run <name> <cmd>      - 🚀 Run command inside anchor directory"
  echo -e "  anc run --filter k=v <cmd> - 🔎 Run command in anchors matching metadata"
}

