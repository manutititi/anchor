#!/usr/bin/env bash

anc_handle_pull() {
    local anchor="$1"
    local server="${2:-$(anc server name 2>/dev/null || echo http://localhost:17017)}"
    local anchor_file="$ANCHOR_DIR/$anchor.json"

    if [[ -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc pull <anchor> [server_url]"
        return 1
    fi

    if [[ -f "$anchor_file" ]]; then
        echo -e "${YELLOW}⚠️ Anchor '$anchor' already exists at $anchor_file${RESET}"
        read -rp "🔁 Overwrite it? [y/N]: " confirm
        confirm="${confirm,,}"  # lowercase
        if [[ "$confirm" != "y" && "$confirm" != "yes" ]]; then
            echo -e "${RED}❌ Pull cancelled.${RESET}"
            return 1
        fi
    fi

    echo -e "${BLUE}⬇️  Downloading '$anchor' from $server...${RESET}"
    curl -sSf "$server/anchors/${anchor}" -o "$anchor_file"

    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}✅ Anchor '$anchor' pulled successfully to $anchor_file${RESET}"
    else
        echo -e "${RED}❌ Failed to pull anchor '$anchor' from $server${RESET}"
        return 1
    fi
}
