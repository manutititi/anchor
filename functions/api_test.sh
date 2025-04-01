#!/usr/bin/env bash

anc_handle_api_test() {
  local name="$1"
  local file="$ANCHOR_DIR/$name"

  if [[ -z "$name" ]]; then
    echo "Usage: anc api-test <name>"
    return 1
  fi

  if [[ ! -f "$file" ]]; then
    echo "❌ Anchor '$name' not found."
    return 1
  fi

  local base_url
  base_url=$(jq -r '.endpoint.base_url' "$file")
  local auth_enabled
  auth_enabled=$(jq -r '.endpoint.auth.enabled' "$file")
  local auth_token_env
  auth_token_env=$(jq -r '.endpoint.auth.token_env' "$file")

  local routes_len
  routes_len=$(jq '.endpoint.routes | length' "$file")

  if [[ "$routes_len" -eq 0 ]]; then
    echo "⚠️ No test routes defined for '$name'."
    return 0
  fi

  echo "🔍 Testing $routes_len route(s) for '$name'..."

  jq -c '.endpoint.routes[]' "$file" | while read -r route; do
    local method path expect params url
    method=$(echo "$route" | jq -r '.method')
    path=$(echo "$route" | jq -r '.path')
    expect=$(echo "$route" | jq -r '.expect.status // 200')

    # Expand path variables with params
    params=$(echo "$route" | jq -r '.params // {} | to_entries[] | "\(.key)=\(.value)"')
    for pair in $params; do
      key="${pair%%=*}"
      value="${pair#*=}"
      path="${path//\{$key\}/$value}"
    done

    url="$base_url$path"
    
    # Build curl command
    local cmd=(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url")

    # Add Authorization header if needed
    if [[ "$auth_enabled" == "true" && -n "${!auth_token_env}" ]]; then
      cmd+=( -H "Authorization: Bearer ${!auth_token_env}" )
    fi

    # Run test
    local status
    status=$("${cmd[@]}")

    if [[ "$status" == "$expect" ]]; then
      echo "✅ $method $path → $status"
    else
      echo "❌ $method $path → $status (expected $expect)"
    fi
  done
}

