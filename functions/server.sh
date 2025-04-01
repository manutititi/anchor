anc_server_name() {
    local server_dir="$(dirname "${BASH_SOURCE[0]}")/../server"
    local server_file="$server_dir/info.json"

    mkdir -p "$server_dir"

    if [[ -z "$1" ]]; then
        # Mostrar la URL actual
        if [[ -f "$server_file" ]]; then
            jq -r '.url' "$server_file"
        else
            echo "http://localhost:17017"
        fi
    else
        local url="$1"

        # Respaldar el archivo actual si existe
        if [[ -f "$server_file" ]]; then
            local timestamp
            timestamp=$(date +%Y%m%d%H%M%S)
            cp "$server_file" "$server_dir/.oldserver_$timestamp.json"
        fi

        # Guardar el nuevo server
        jq -n --arg url "$url" '{url: $url}' > "$server_file"
    fi
}




anc_server_ls() {
    local server="${3:-$(anc server name 2>/dev/null || echo http://localhost:17017)}"

    #anc server ls <name>
    if [[ "$1" != "-f" && "$1" != "--filter" && -n "$1" ]]; then
        local anchor="$1"
        local url="$server/anchors/$anchor/raw"
        
        curl -s -f "$url" | jq .
        return
    fi

    # anc server ls -f key=value
    local filter=""
    if [[ "$1" == "-f" || "$1" == "--filter" ]]; then
        filter="$2"
    fi

    local url="$server/anchors"
    if [[ -n "$filter" ]]; then
        local encoded
        encoded=$(printf "%s" "$filter" | jq -s -R -r @uri)
        url="$url?filter=$encoded"
    fi

    echo "🌐 Listing anchors from $server..."

    local anchors
    mapfile -t anchors < <(curl -s -f "$url" | jq -r '.[]')

    if [[ ${#anchors[@]} -eq 0 ]]; then
        echo "⚠️  No anchors found."
        return
    fi

    for anchor in "${anchors[@]}"; do
        local meta
        meta=$(curl -s -f "$server/anchors/$anchor/raw" || echo "{}")

        local path type note env project
        path=$(echo "$meta" | jq -r '.path // empty')
        type=$(echo "$meta" | jq -r '.type // empty')
        note=$(echo "$meta" | jq -r '.note // empty')
        env=$(echo "$meta" | jq -r '.env // empty')
        project=$(echo "$meta" | jq -r '.project // empty')

        local description=""
        [[ -n "$project" ]] && description+="📦 $project "
        [[ -n "$env" ]]     && description+="🌱 $env "
        [[ -n "$note" ]]    && description+="📝 $note"

        printf "  ⚓ %-18s → %-40s %s\n" "$anchor" "${path:-($type)}" "$description"
    done
}




anc_server_status() {
  local server
  server="$(anc server name 2>/dev/null || echo http://localhost:17017)"

  echo "🌐 Server: $server"

  # Check reachability
  if curl -s --connect-timeout 2 "$server/anchors" > /dev/null; then
    echo "✅ Server is reachable"

    # Get number of anchors
    local count
    count=$(curl -s "$server/anchors" | jq 'length')
    echo "📁 Remote anchors: $count"
  else
    echo "❌ Cannot reach server"
  fi
}
















anc_server() {
    case "$1" in
        name)
            shift
            anc_server_name "$@"
            ;;
        ls | show)
            shift
            anc_server_ls "$@"
            ;;

        status)
            anc_server_status
            ;;


        *)
            echo "Unknown server command: $1"
            ;;
    esac
}
