#!/usr/bin/env bash

ANCHOR_DIR="${ANCHOR_DIR:-"$ANCHOR_ROOT/data"}"

anc_env_apply() {
  local env_name=""
  local no_link=false

  # Procesar argumentos
  for arg in "$@"; do
    case "$arg" in
      --no-link)
        no_link=true
        ;;
      *)
        env_name="$arg"
        ;;
    esac
  done

  # Si no se pasa nombre, intentar leer .anc_env
  if [[ -z "$env_name" ]]; then
    if [[ -f .anc_env ]]; then
      env_name=$(<.anc_env)
      env_name="${env_name//[$'\t\r\n ']}"
      echo "📄 Found .anc_env → Using environment: $env_name"
    else
      echo "❌ Usage: anc env <name> [--no-link]"
      echo "   Or ensure .anc_env exists in current directory"
      return 1
    fi
  fi

  local env_file="$ANCHOR_DIR/$env_name.json"
  if [[ ! -f "$env_file" ]]; then
    echo "❌ Environment '$env_name' not found at $env_file"
    return 1
  fi

  local type
  type=$(jq -r '.type // empty' "$env_file")
  if [[ "$type" != "env" ]]; then
    echo "❌ '$env_name' is not a valid environment anchor (type != env)"
    return 1
  fi

  if ! $no_link; then
    echo "$env_name" > .anc_env
    echo "📎 Linked current directory to env '$env_name' via .anc_env"
  fi

  echo "📦 Applying environment: $env_name"

  local vars_keys
  vars_keys=$(jq -r '.vars | keys[]?' "$env_file")
  for key in $vars_keys; do
    local value
    value=$(jq -r --arg k "$key" '.vars[$k]' "$env_file")
    export "$key=$value"

    if [[ "$key" == "API_TOKEN" || "$key" == "SECRET_KEY" ]]; then
      echo "  🔐 $key=**********"
    else
      echo "  🔑 $key=$value"
    fi
  done

  anc_run_scripts "$env_file" "preload" || return 1
  anc_run_scripts "$env_file" "postload" || return 1

  echo "✅ Environment '$env_name' applied."
}


anc_run_scripts() {
  local env_file="$1"
  local label="$2"

  if jq -e --arg l "$label" ".scripts[\$l] | type == \"string\"" "$env_file" >/dev/null 2>&1; then
    local script
    script=$(jq -r ".scripts[\"$label\"]" "$env_file")
    anc_run_script "$script" "$label" || return 1
  elif jq -e --arg l "$label" ".scripts[\$l] | type == \"array\"" "$env_file" >/dev/null 2>&1; then
    jq -r ".scripts[\"$label\"][]" "$env_file" | while read -r script; do
      anc_run_script "$script" "$label" || return 1
    done
  fi
}

anc_run_script() {
  local script="$1"
  local label="$2"
  local resolved=""

  if [[ "$script" =~ ^/ ]] && [[ -x "$script" ]]; then
    resolved="$script"
  elif [[ -x "$script" ]]; then
    resolved="$script"
  elif [[ -x "./scripts/$script" ]]; then
    resolved="./scripts/$script"
  elif [[ -n "$ANCHOR_ROOT" && -x "$ANCHOR_ROOT/scripts/$script" ]]; then
    resolved="$ANCHOR_ROOT/scripts/$script"
  fi

  if [[ -n "$resolved" ]]; then
    echo "▶️  Running $label script: $resolved"
    "$resolved"
    local code=$?
    if [[ "$code" -ne 0 ]]; then
      echo "❌ $label script '$script' failed with exit code $code"
      return 1
    fi
  else
    echo "⚠️  $label script '$script' not found or not executable"
    return 1
  fi
}
