# functions/push.sh

anc_handle_push() {
    local anchor="$1"
    local server="${2:-http://localhost:17017}"
    local anchor_file="$ANCHOR_DIR/$anchor"

    if [[ -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc push <anchor> [server_url]"
        return 1
    fi

    if [[ ! -f "$anchor_file" ]]; then
        echo -e "${RED}❌ Anchor '$anchor' not found at $anchor_file${RESET}"
        return 1
    fi

    # Crear archivo temporal con extensión .json para cumplir con el server
    local tmp_file
    tmp_file=$(mktemp --suffix=.json)
    cp "$anchor_file" "$tmp_file"

    echo -e "${BLUE}⬆️  Uploading anchor '$anchor' to $server...${RESET}"
    curl -s -X POST "$server/anchors/$anchor" -F "file=@$tmp_file"

    local exit_code=$?
    rm -f "$tmp_file"

    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}✅ Anchor '$anchor' pushed successfully${RESET}"
    else
        echo -e "${RED}❌ Upload failed${RESET}"
    fi
}

