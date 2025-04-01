#!/usr/bin/env bash

anc_handle_export() {
  local name="$1"
  local format="$2"
  local file="$ANCHOR_DIR/$name"

  if [[ -z "$name" || -z "$format" ]]; then
    echo "Usage: anc export <name> <format: json|http|md|postman>"
    return 1
  fi

  if [[ ! -f "$file" ]]; then
    echo "❌ Anchor '$name' not found."
    return 1
  fi

  case "$format" in
    json)
      cat "$file"
      ;;

    http)
      local base_url method path
      base_url=$(jq -r '.endpoint.base_url' "$file")
      jq -c '.endpoint.routes[]' "$file" | while read -r route; do
        method=$(echo "$route" | jq -r '.method')
        path=$(echo "$route" | jq -r '.path')
        echo -e "### $method $path"
        echo "$method $base_url$path"
        echo "Content-Type: application/json"
        echo
      done
      ;;

    md)
      echo "# Anchor: $name"
      echo
      jq -r '.meta | to_entries[] | "- \(.key): \(.value)"' "$file"
      echo
      echo "## Endpoints"
      jq -c '.endpoint.routes[]' "$file" | while read -r route; do
        method=$(echo "$route" | jq -r '.method')
        path=$(echo "$route" | jq -r '.path')
        status=$(echo "$route" | jq -r '.expect.status // "?"')
        echo "### \`$method $path\`"
        echo "- Expected status: $status"
        echo
      done
      ;;

    postman)
      local uuid host port raw_url
      uuid=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid)
      raw_url=$(jq -r '.endpoint.base_url' "$file")
      host=$(echo "$raw_url" | awk -F[/:] '{print $4}')
      port=$(echo "$raw_url" | awk -F[/:] '{print $5}')
      if [[ -z "$port" ]]; then port="80"; fi

      jq --arg name "$name" \
         --arg id "$uuid" \
         --arg raw_url "$raw_url" \
         --arg host "$host" \
         --arg port "$port" \
         '  {
              info: {
                name: $name,
                _postman_id: $id,
                schema: "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
              },
              item: (.endpoint.routes | map({
                name: (.name // (.method + " " + .path)),
                request: {
                  method: .method,
                  header: [],
                  url: {
                    raw: ($raw_url + .path),
                    host: [$host],
                    port: $port,
                    path: (.path | split("/") | map(select(. != "")))
                  }
                }
              }))
            }' "$file"
      ;;

    *)
      echo "❌ Unsupported format: $format"
      return 1
      ;;
  esac
}
