# functions/pull.sh

anc_handle_pull() {
    local anchor="$1"
    local server="${2:-http://localhost:8000}"
    local output_file="$ANCHOR_DIR/$anchor"

    if [[ -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc pull <anchor> [server_url]"
        return 1
    fi

    mkdir -p "$ANCHOR_DIR"

    echo -e "${BLUE}🔽 Downloading anchor '$anchor' from $server...${RESET}"

    curl -s -f "$server/anchors/$anchor" -o "$output_file"
    local result=$?

    if [[ $result -eq 0 ]]; then
        echo -e "${GREEN}✅ Anchor '$anchor' downloaded to $output_file${RESET}"
    else
        echo -e "${RED}❌ Failed to download anchor '$anchor' from $server${RESET}"
    fi
}

