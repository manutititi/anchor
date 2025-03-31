# functions/pull.sh

anc_handle_pull() {
    local arg1="$1"
    local arg2="$2"
    local server="${3:-$(anc server name 2>/dev/null || echo http://localhost:17017)}"

    # Asegurar ANCHOR_DIR correctamente
    export ANCHOR_ROOT="${ANCHOR_ROOT:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"}"
    export ANCHOR_DIR="${ANCHOR_DIR:-"$ANCHOR_ROOT/data"}"

    if [[ "$arg1" == "--all" ]]; then
        echo "📥 Pulling all anchors from $server"
        mapfile -t anchors < <(curl -s "$server/anchors" | jq -r '.[]')
        for anchor in "${anchors[@]}"; do
            anc_pull_anchor "$anchor" "$server"
        done

    elif [[ "$arg1" == "--filter" || "$arg1" == "-f" ]]; then
        local filter="$arg2"
        local encoded_filter
        encoded_filter=$(printf "%s" "$filter" | jq -s -R -r @uri)

        echo "📥 Pulling anchors from $server matching filter: $filter"
        mapfile -t anchors < <(curl -s "$server/anchors?filter=$encoded_filter" | jq -r '.[]')
        for anchor in "${anchors[@]}"; do
            anc_pull_anchor "$anchor" "$server"
        done

    elif [[ -n "$arg1" ]]; then
        echo "📥 Pulling anchor '$arg1' from $server"
        anc_pull_anchor "$arg1" "$server"

    else
        echo "❌ Missing anchor name or flag. Use:"
        echo "   anc pull <name>"
        echo "   anc pull --all"
        echo "   anc pull --filter key=value"
    fi
}

anc_pull_anchor() {
    local anchor="$1"
    local server="$2"
    local url="$server/anchors/$anchor"

    local dest="$ANCHOR_DIR/$anchor"

    echo "   ⬇️  $anchor → $dest"
    if ! curl -s -f "$url" -o "$dest"; then
        echo "   ⚠️  Failed to pull $anchor"
    fi
}

