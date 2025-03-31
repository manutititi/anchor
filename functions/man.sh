anc_handle_man(){

#!/usr/bin/env bash

BOLD="\033[1m"
RESET="\033[0m"
CYAN="\033[1;36m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[1;34m"
GRAY="\033[0;90m"

echo -e "${BOLD}📖 anc - Quick Usage Guide${RESET}\n"

echo -e "${CYAN}🎯 Basic Navigation:${RESET}"
echo -e "  ⚓ anc                         ${GRAY}# Jump to the 'default' anchor${RESET}"
echo -e "  ⚓ anc test                   ${GRAY}# Jump to the 'test' anchor${RESET}"
echo -e "  📂 anc test ls                ${GRAY}# List contents of the anchor directory${RESET}"
echo -e "  🌲 anc test tree              ${GRAY}# Show tree view of the anchor${RESET}"
echo -e "  🔍 anc show test             ${GRAY}# Show metadata and path for an anchor${RESET}"
echo

echo -e "${CYAN}🛠️  Anchor Management:${RESET}"
echo -e "  📍 anc set                    ${GRAY}# Set anchor for current directory${RESET}"
echo -e "  📍 anc set ./folder           ${GRAY}# Set anchor for a relative path${RESET}"
echo -e "  🌐 anc set-ssh test ssh://user@host:/path   ${GRAY}# Set a remote SSH anchor${RESET}"
echo -e "  🗑️  anc del test              ${GRAY}# Delete an anchor${RESET}"
echo -e "  🔄 anc rename old new        ${GRAY}# Rename an anchor${RESET}"
echo -e "  🧹 anc prune                 ${GRAY}# Remove anchors pointing to non-existent paths${RESET}"
echo -e "  📝 anc note test 'project folder'    ${GRAY}# Add or update note for an anchor${RESET}"
echo -e "  🧩 anc meta test env=dev project=demo ${GRAY}# Assign metadata to anchor${RESET}"
echo

echo -e "${CYAN}📂 File Transfer:${RESET}"
echo -e "  📥 anc cp file.txt test/     ${GRAY}# Copy file to anchor${RESET}"
echo -e "  🚚 anc mv file.txt test/     ${GRAY}# Move file to anchor${RESET}"
echo -e "  🔁 anc cpt main/app.sh test/bin/   ${GRAY}# Copy between anchors${RESET}"
echo

echo -e "${CYAN}▶️  Running Commands:${RESET}"
echo -e "  🚀 anc run test make build   ${GRAY}# Run command inside an anchor directory${RESET}"
echo -e "  🔎 anc run -f env=dev 'ls -la' ${GRAY}# Run command in filtered anchors${RESET}"
echo

echo -e "${CYAN}🌐 Server Sync:${RESET}"
echo -e "  ⬆️  anc push test             ${GRAY}# Push anchor metadata to server${RESET}"
echo -e "  ⬇️  anc pull test             ${GRAY}# Pull metadata for a specific anchor${RESET}"
echo -e "  ⬇️  anc pull --all            ${GRAY}# Pull all remote anchors${RESET}"
echo -e "  ⬇️  anc pull -f env=dev       ${GRAY}# Pull anchors matching metadata${RESET}"
echo

echo -e "  🌍 anc server name [url]      ${GRAY}# Set or show current server URL${RESET}"
echo -e "  📋 anc server ls              ${GRAY}# List all anchors on the server${RESET}"
echo -e "  📋 anc server ls -f project=demo ${GRAY}# Filter server anchors by metadata${RESET}"
echo -e "  🔍 anc server ls test         ${GRAY}# Show raw metadata for one anchor${RESET}"
echo -e "  🌐 http://localhost:17017/dashboard ${GRAY}# Browse all anchors in the web dashboard${RESET}"
echo -e "  ${YELLOW}⚙️  Tip: You can combine filters with AND / OR, like:${RESET}"
echo -e "     anc server ls -f 'env=dev AND project=demo'"





}
