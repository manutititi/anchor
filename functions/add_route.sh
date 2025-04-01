#!/usr/bin/env bash

anc_handle_add_route() {
  local name="$1"
  local method="$2"
  local path="$3"
  shift 3

  local expected_status=200
  declare -A params

  for arg in "$@"; do
    if [[ "$arg" =~ ^[a-zA-Z0-9_]+=.*$ ]]; then
      key="${arg%%=*}"
      value="${arg#*=}"
      params["$key"]="$value"
    elif [[ "$arg" =~ ^[0-9]{3}$ ]]; then
      expected_status="$arg"
    fi
  done

  if [[ -z "$name" || -z "$method" || -z "$path" ]]; then
    echo "Usage: anc add-route <name> <method> <path> [param1=val1 ...] [expected_status]"
    return 1
  fi

  local file="$ANCHOR_DIR/$name"
  if [[ ! -f "$file" ]]; then
    echo "❌ Anchor '$name' not found."
    return 1
  fi

  local jq_params="{}"
  for key in "${!params[@]}"; do
    jq_params=$(echo "$jq_params" | jq --arg k "$key" --arg v "${params[$key]}" '. + {($k): $v}')
  done

  local updated_json
  updated_json=$(jq \
    --arg method "$method" \
    --arg path "$path" \
    --arg expect "$expected_status" \
    --argjson params "$jq_params" \
    '.endpoint.routes += [{
      name: ($method + " " + $path),
      method: $method,
      path: $path,
      params: $params,
      expect: { status: ($expect | tonumber) }
    }]' "$file")

  echo "$updated_json" > "$file"
  echo "✅ Route added to '$name': $method $path → expect $expected_status"
}
