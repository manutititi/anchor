#!/usr/bin/env bash

anc_handle_push() {
    local name="$1"
    local server="${2:-$(anc server name 2>/dev/null || echo http://localhost:17017)}"

    if [[ -z "$name" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc push <anchor> [server_url]"
        return 1
    fi

    # Forzar extensión .json si no la tiene
    [[ "$name" != *.json ]] && name="${name}.json"

    local anchor_file="$ANCHOR_DIR/$name"

    if [[ ! -f "$anchor_file" ]]; then
        echo -e "${RED}❌ Anchor '$name' not found at $anchor_file${RESET}"
        return 1
    fi

    echo -e "${BLUE}⬆️  Uploading '$name' to $server...${RESET}"
    local response
    response=$(curl -s -w "%{http_code}" -X POST "$server/anchors/_upload" -F "file=@$anchor_file")
    local status="${response: -3}"
    local body="${response:: -3}"

    if [[ "$status" == "200" || "$status" == "201" ]]; then
        echo -e "${GREEN}✅ '$name' pushed successfully${RESET}"
    else
        echo -e "${RED}❌ Upload failed (${status})${RESET}"
        echo -e "${YELLOW}Server response:${RESET} $body"
        return 1
    fi
}
