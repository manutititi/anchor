#!/usr/bin/env bash

anc_handle_help() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local CYAN="\033[1;36m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"

  echo -e "${BOLD}📖 anc - Simple anchor system for directories, environments, and APIs${RESET}\n"

  echo -e "${CYAN}🎯 Navigation:${RESET}"
  echo -e "  anc                          - ⚓ Go to default anchor"
  echo -e "  anc <name>                  - ⚓ Jump to anchor"
  echo -e "  anc <name> ls               - 📂 List contents of anchor directory"
  echo -e "  anc <name> tree             - 🌲 Tree view of anchor directory"
  echo -e "  anc show <name>             - 🔍 Show full metadata of anchor"
  echo -e "  anc ls [-e|-u|-f k=v]       - 📌 List anchors (envs, URLs, or filtered)"
  echo

  echo -e "${CYAN}🛠️  Anchor Management:${RESET}"
  echo -e "  anc set [--rel] [name]            - 📍 Set local anchor to current directory"
  echo -e "  anc set --env <name> [.env]       - 🧪 Create environment anchor"
  echo -e "  anc set --url <name> <url>        - 🌍 Create web/API anchor"
  echo -e "  anc set --server <url>            - 🛰️  Set remote anchor server URL"
  echo -e "  anc del <name>                    - 🗑️  Delete anchor"
  echo -e "  anc rename <old> <new>            - 🔄 Rename anchor"
  echo -e "  anc prune                         - 🧹 Remove anchors pointing to non-existent directories"
  echo -e "  anc note <name> [msg]             - 📝 Add or update note"
  echo -e "  anc meta <name> k=v ...           - 🧩 Set or override metadata"
  echo

  echo -e "${CYAN}📂 File Transfer:${RESET}"
  echo -e "  anc cp <file...> <anchor[/subpath]>        - 📥 Copy file(s) to anchor"
  echo -e "  anc mv <file...> <anchor[/subpath]>        - 🚚 Move file(s) to anchor"
  echo -e "  anc cpt <from-anchor[/path]> <to-anchor[/path]> - 🔁 Copy between anchors"
  echo

  echo -e "${CYAN}▶️  Execute Commands:${RESET}"
  echo -e "  anc run <anchor> <cmd>                    - 🚀 Run command inside anchor"
  echo -e "  anc run --filter k=v <cmd>                - 🔎 Run command in anchors matching metadata"
  echo

  echo -e "${CYAN}🌐 URL Anchors / API:${RESET}"
  echo -e "  anc url -a <anchor> [method] [path] [params] [status]     - ➕ Add route"
  echo -e "  anc url -d <anchor>                                       - 🗑️  Delete route"
  echo -e "  anc url -t <anchor>                                       - 🧪 Test defined routes"
  echo -e "  anc url -c <anchor> <method> [path] [data|file]           - 🌐 Call API # development"
  echo -e "    Supports JSON, file uploads (-F), env token injection"
  echo

  echo -e "${CYAN}🌐 Server Sync:${RESET} # development"
  echo -e "  anc pull <name>                      - ⬇️  Download anchor from server"
  echo -e "  anc pull --all                       - ⬇️  Download all remote anchors"
  echo -e "  anc pull -f key=value                - ⬇️  Filter and download"
  echo -e "  anc server ls                        - 📋 List anchors on remote"
  echo -e "  anc server ls -f key=value           - 📋 Filter remote anchors"
  echo -e "  anc server ls <name>                 - 🔍 Show raw remote anchor metadata"
  echo

  echo -e "${CYAN}📦 Environments:${RESET}"
  echo -e "  anc env <name>                - 📥 Apply env vars from anchor and link it"
  echo

  echo -e "${CYAN}📤 Export:${RESET}"
  echo -e "  anc export <name> <format>          - 🔄 Export anchor (json, markdown, postman, etc)"
  echo

  echo -e "${CYAN}♻️  Reconstruction:${RESET}"
  echo -e "  anc rc <anchor> [target_path]       - 🧬 Recreate full environment from anchor metadata"
}
