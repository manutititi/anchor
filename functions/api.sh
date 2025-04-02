#!/usr/bin/env bash

anc_handle_api() {
  if [[ "$1" == "ls" ]]; then
    local name="$2"
    local file="$ANCHOR_DIR/$name"

    if [[ -z "$name" ]]; then
      echo "Usage: anc api ls <name>"
      return 1
    fi

    if [[ ! -f "$file" ]]; then
      echo "❌ Anchor '$name' not found."
      return 1
    fi

    local routes_len
    routes_len=$(jq '.endpoint.routes | length' "$file")

    if [[ "$routes_len" -eq 0 ]]; then
      echo "⚠️ No API routes defined for '$name'."
      return 0
    fi

    echo "📋 API routes for '$name':"
    jq -r '.endpoint.routes[] | "  - \(.method) \(.path)"' "$file"
    return
  fi

  local name="$1"
  local path="$2"
  local method="${3:-GET}"
  shift 3

  local file="$ANCHOR_DIR/$name"
  if [[ ! -f "$file" ]]; then
    echo "❌ Anchor '$name' not found."
    return 1
  fi

  local base_url auth_enabled token_env
  base_url=$(jq -r '.endpoint.base_url' "$file")
  auth_enabled=$(jq -r '.endpoint.auth.enabled // false' "$file")
  token_env=$(jq -r '.endpoint.auth.token_env // ""' "$file")

  local full_url="$base_url$path"
  local headers=("Accept: application/json" "Content-Type: application/json")
  local curl_cmd=(curl -s -X "$method" "$full_url")

  # Add headers
  for h in "${headers[@]}"; do
    curl_cmd+=( -H "$h" )
  done

  # Auth if required and token available
  if [[ "$auth_enabled" == "true" && -n "$token_env" && -n "${!token_env}" ]]; then
    curl_cmd+=( -H "Authorization: Bearer ${!token_env}" )
  elif [[ "$auth_enabled" == "true" && -n "$token_env" && -z "${!token_env}" ]]; then
    echo "⚠️ Auth enabled but env var '$token_env' not set. Skipping token header."
  fi

  # If there are extra args, treat them as data or params
  if [[ "$method" =~ ^(POST|PUT|PATCH)$ ]]; then
    if [[ -n "$1" ]]; then
      curl_cmd+=( -d "$1" )
    fi
  fi

  echo "🌐 $method $full_url"
  "${curl_cmd[@]}"
}

