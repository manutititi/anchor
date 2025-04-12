#!/usr/bin/env bash

ANCHOR_DIR="${ANCHOR_DIR:-"$ANCHOR_ROOT/data"}"

anc_handle_env() {
  local subcommand="$1"
  shift

  case "$subcommand" in
    apply)
      anc_env_apply "$@"
      ;;
    *)
      echo "Usage: anc env apply <name>"
      ;;
  esac
}

anc_env_apply() {
  local env_name="$1"
  if [[ -z "$env_name" ]]; then
    echo "Usage: anc env apply <name>"
    return 1
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

  echo "📦 Applying environment: $env_name"

  # Exportar variables
  local vars_keys
  vars_keys=$(jq -r '.vars | keys[]' "$env_file")

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

  # Ejecutar scripts preload
  if jq -e '.scripts.preload | type == "string"' "$env_file" >/dev/null 2>&1; then
    local script
    script=$(jq -r '.scripts.preload' "$env_file")
    anc_run_script "$script" "preload" || return 1
  elif jq -e '.scripts.preload | type == "array"' "$env_file" >/dev/null 2>&1; then
    jq -r '.scripts.preload[]' "$env_file" | while read -r script; do
      anc_run_script "$script" "preload" || return 1
    done
  fi

  # Ejecutar scripts postload
  if jq -e '.scripts.postload | type == "string"' "$env_file" >/dev/null 2>&1; then
    local script
    script=$(jq -r '.scripts.postload' "$env_file")
    anc_run_script "$script" "postload" || return 1
  elif jq -e '.scripts.postload | type == "array"' "$env_file" >/dev/null 2>&1; then
    jq -r '.scripts.postload[]' "$env_file" | while read -r script; do
      anc_run_script "$script" "postload" || return 1
    done
  fi

  echo "✅ Environment '$env_name' applied."
}

anc_run_script() {
  local script="$1"
  local label="$2"
  local resolved=""

  # Si es ruta absoluta y ejecutable
  if [[ "$script" =~ ^/ ]] && [[ -x "$script" ]]; then
    resolved="$script"
  # Si es ejecutable relativo al directorio actual
  elif [[ -x "$script" ]]; then
    resolved="$script"
  # Si existe en ./scripts/
  elif [[ -x "./scripts/$script" ]]; then
    resolved="./scripts/$script"
  # Si existe en $ANCHOR_ROOT/scripts/
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
