#!/usr/bin/env bash

anc_handle_copy_or_move() {
  local cmd="$1"
  shift

  if [[ "$#" -lt 2 ]]; then
    echo -e "${YELLOW}Usage:${RESET} anc $cmd <source(s)> <destination>${RESET}"
    return 1
  fi

  local destination="${@: -1}"
  local sources=("${@:1:$#-1}")

  # --- Preparar destino
  local dest_anchor="${destination%%/*}"
  local dest_subpath="${destination#*/}"
  [[ "$destination" == "$dest_anchor" ]] && dest_subpath=""
  local dest_meta="$ANCHOR_DIR/$dest_anchor.json"
  local dest_path=""
  local dest_is_ssh=false
  local dest_ssh_prefix=""
  local dest_rsync_target=""

  if [[ -f "$dest_meta" ]]; then
    local dest_type=$(jq -r '.type' "$dest_meta")
    if [[ "$dest_type" == "ssh" ]]; then
      dest_is_ssh=true
      local ssh_host=$(jq -r '.host' "$dest_meta")
      local ssh_user=$(jq -r '.user' "$dest_meta")
      local ssh_port=$(jq -r '.port // 22' "$dest_meta")
      local ssh_key=$(jq -r '.identity_file // empty' "$dest_meta")
      local ssh_base=$(jq -r '.path // "~"' "$dest_meta")

      if [[ "$ssh_base" == "~" || -z "$ssh_base" ]]; then
        dest_path="$dest_subpath"
      else
        dest_path="$ssh_base"
        [[ -n "$dest_subpath" ]] && dest_path="$dest_path/$dest_subpath"
        dest_path=$(realpath -m "$dest_path")
      fi

      dest_ssh_prefix="${ssh_user}@${ssh_host}"
      dest_rsync_target="${dest_ssh_prefix}:${dest_path:+$dest_path/}"
    else
      dest_path=$(jq -r '.path // empty' "$dest_meta")
      [[ "$dest_path" == ~* ]] && dest_path="${dest_path/#\~/$HOME}"
      dest_path=$(realpath -m "$dest_path")
      [[ -n "$dest_subpath" ]] && dest_path="$dest_path/$dest_subpath"
    fi
  else
    [[ "$destination" == ~* ]] && destination="${destination/#\~/$HOME}"
    dest_path=$(realpath -m "$destination")
  fi

  [[ "$dest_is_ssh" == false ]] && mkdir -p "$dest_path" || true

  for src in "${sources[@]}"; do
    local src_anchor="${src%%/*}"
    local src_subpath="${src#*/}"
    [[ "$src" == "$src_anchor" ]] && src_subpath=""

    local src_meta="$ANCHOR_DIR/$src_anchor.json"
    local src_is_ssh=false
    local src_ssh_prefix=""
    local src_rsync_source=""
    local src_path=""

    if [[ -f "$src_meta" ]]; then
      local src_type=$(jq -r '.type' "$src_meta")
      if [[ "$src_type" == "ssh" ]]; then
        src_is_ssh=true
        local ssh_host=$(jq -r '.host' "$src_meta")
        local ssh_user=$(jq -r '.user' "$src_meta")
        local ssh_port=$(jq -r '.port // 22' "$src_meta")
        local ssh_key=$(jq -r '.identity_file // empty' "$src_meta")
        local ssh_base=$(jq -r '.path // "~"' "$src_meta")

        if [[ "$ssh_base" == "~" || -z "$ssh_base" ]]; then
          src_path="$src_subpath"
        else
          src_path="$ssh_base"
          [[ -n "$src_subpath" ]] && src_path="$src_path/$src_subpath"
          src_path=$(realpath -m "$src_path")
        fi

        src_ssh_prefix="${ssh_user}@${ssh_host}"
        src_rsync_source="${src_ssh_prefix}:${src_path}"
      else
        src_path=$(jq -r '.path // empty' "$src_meta")
        [[ "$src_path" == ~* ]] && src_path="${src_path/#\~/$HOME}"
        src_path=$(realpath -m "$src_path")
        [[ -n "$src_subpath" ]] && src_path="$src_path/$src_subpath"
      fi
    else
      [[ "$src" == ~* ]] && src="${src/#\~/$HOME}"
      src_path=$(realpath -m "$src")
    fi

    if [[ "$src_is_ssh" == true && "$dest_is_ssh" == true ]]; then
      echo -e "${RED}❌ Copying between two SSH anchors is not supported${RESET}"
      continue
    fi

    # ejecutar transferencia
    if [[ "$cmd" == "mv" ]]; then
      echo -e "${YELLOW}⚠️ Remote 'mv' not supported yet. Use 'cp' and delete manually.${RESET}"
    fi

    if [[ "$src_is_ssh" == true ]]; then
      # copiar desde remoto a local
      rsync -az -e "ssh -i $ssh_key -p $ssh_port" "$src_rsync_source" "$dest_path/" && \
        echo -e "${GREEN}✅ Copied '$src' to '$dest_path/'${RESET}"
    elif [[ "$dest_is_ssh" == true ]]; then
      # copiar desde local a remoto
      rsync -az -e "ssh -i $ssh_key -p $ssh_port" "$src_path" "$dest_rsync_target" && \
        echo -e "${GREEN}✅ Copied '$src_path' to '$dest_rsync_target'${RESET}"
    else
      # local a local
      rsync -a --progress "$src_path" "$dest_path/" && \
        echo -e "${GREEN}✅ Copied '$src_path' to '$dest_path/'${RESET}"
    fi
  done
}
