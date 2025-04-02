#!/usr/bin/env bash

# Definición del entorno de trabajo
SCRIPT_DIR="${BASH_SOURCE%/*}"
ENV_DIR="${ENV_DIR:-"$ANCHOR_ROOT/envs"}"

anc_handle_env() {
  local subcommand="$1"
  shift

  case "$subcommand" in
    init)
      anc_env_init "$@"
      ;;
    apply)
      anc_env_apply "$@"
      ;;
    *)
      echo "Usage: anc env <init|apply> <name>"
      ;;
  esac
}


anc_env_init() {
  local env_name="$1"
  if [[ -z "$env_name" ]]; then
    echo "Usage: anc env init <name>"
    return 1
  fi

  local env_dir="$ENV_DIR"
  mkdir -p "$env_dir"
  local env_file="$env_dir/$env_name.json"

  if [[ -f "$env_file" ]]; then
    echo "❌ Environment '$env_name' already exists at $env_file"
    return 1
  fi

  local created_at
  created_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  local json
  json=$(jq -n \
    --arg name "$env_name" \
    --arg created_by "$USER" \
    --arg created_at "$created_at" \
    --arg description "" \
    '{
      name: $name,
      vars: {
        API_TOKEN: "",
        DB_URL: "",
        SECRET_KEY: "",
        BASE_URL: "",
        ENV: ""
      },
      scripts: {
        preload: "",
        postload: ""
      },
      meta: {
        created_by: $created_by,
        created_at: $created_at,
        description: $description,
        tags: [],
        shared: false,
        encrypted: false
      }
    }')

  echo "$json" > "$env_file"
  echo "✅ Environment '$env_name' created at $env_file"

  echo "$env_name" > .anc-env
  echo "📎 Linked current directory to env '$env_name' via .anc-env"
}


anc_env_apply() {
  local env_name="$1"
  if [[ -z "$env_name" ]]; then
    echo "Usage: anc env apply <name>"
    return 1
  fi

  local env_file="$ENV_DIR/$env_name.json"
  if [[ ! -f "$env_file" ]]; then
    echo "❌ Environment '$env_name' not found at $env_file"
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

    if [[ "$key" == "API_TOKEN" ]]; then
      echo "  🔐 $key=**********"
    else
      echo "  🔑 $key=$value"
    fi
  done






    # Ejecutar preload si está definido
  local preload
  preload=$(jq -r '.scripts.preload // ""' "$env_file")
  if [[ -n "$preload" && -x "$preload" ]]; then
    echo "▶️  Running preload script: $preload"
    "$preload"
  fi

  echo "✅ Environment '$env_name' applied."
}

