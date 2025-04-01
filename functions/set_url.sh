#!/usr/bin/env bash

anc_handle_set_url() {
  local name="$1"
  local base_url="$2"

  if [[ -z "$name" || -z "$base_url" ]]; then
    echo "Usage: anc set-url <name> <base_url>"
    return 1
  fi

  local file="$ANCHOR_DIR/$name"

  if [[ -f "$file" ]]; then
    echo "⚠️ Anchor '$name' already exists at: $file"
    echo "Use anc meta or anc add-route to extend it."
    return 1
  fi

  local created_at
  created_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  local json
  json=$(jq -n \
    --arg name "$name" \
    --arg url "$base_url" \
    --arg created_by "$USER" \
    --arg created_at "$created_at" \
    ' {
      type: "url",
      name: $name,
      meta: {
        project: "",
        env: "",
        note: "",
        created_by: $created_by,
        created_at: $created_at
      },
      endpoint: {
        base_url: $url,
        version: "v1",
        auth: {
          enabled: false,
          type: "bearer",
          token_env: "API_TOKEN"
        },
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/json"
        },
        routes: []
      },
      interfaces: {
        docs: "",
        dashboard: ""
      },
      automation: {
        test_enabled: true,
        scan_enabled: false,
        tools: []
      }
    }')

  echo "$json" > "$file"
  echo "✅ Anchor '$name' created as type 'url'"
  echo "🌐 Base URL: $base_url"
  echo "💡 You can now add routes with add-route"
}

