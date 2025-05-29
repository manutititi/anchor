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
        dest_path="$dest_subpath"  # equivale a $HOME/subpath remoto
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
    if [[ "$src" == */* && -f "$ANCHOR_DIR/${src%%/*}.json" ]]; then
      local anchor="${src%%/*}"
      local pattern="${src#*/}"
      local anchor_path=$(jq -r '.path // empty' "$ANCHOR_DIR/$anchor.json")
      [[ "$anchor_path" == ~* ]] && anchor_path="${anchor_path/#\~/$HOME}"
      anchor_path=$(realpath -m "$anchor_path")

      shopt -s nullglob
      local matched_files=("$anchor_path"/$pattern)
      shopt -u nullglob

      if [[ "${#matched_files[@]}" -eq 0 ]]; then
        echo -e "${YELLOW}⚠️ No files matched pattern '$pattern' in anchor '$anchor'${RESET}"
        continue
      fi

      for matched in "${matched_files[@]}"; do
        if [[ "$cmd" == "mv" ]]; then
          if [[ "$dest_is_ssh" == true ]]; then
            rsync -az -e "ssh -i $ssh_key -p $ssh_port" "$matched" "$dest_rsync_target" && rm "$matched" && \
              echo -e "${GREEN}✅ Moved '$matched' to '$dest_rsync_target'${RESET}"
          else
            mv "$matched" "$dest_path/" && echo -e "${GREEN}✅ Moved '$matched' to '$dest_path/'${RESET}"
          fi
        else
          if [[ "$dest_is_ssh" == true ]]; then
            rsync -az -e "ssh -i $ssh_key -p $ssh_port" "$matched" "$dest_rsync_target" && \
              echo -e "${GREEN}✅ Copied '$matched' to '$dest_rsync_target'${RESET}"
          else
            rsync -a --progress "$matched" "$dest_path/" && echo -e "${GREEN}✅ Copied '$matched' to '$dest_path/'${RESET}"
          fi
        fi
      done
      continue
    fi

    local src_path=""
    if [[ -f "$ANCHOR_DIR/$src.json" ]]; then
      src_path=$(jq -r '.path // empty' "$ANCHOR_DIR/$src.json")
      [[ "$src_path" == ~* ]] && src_path="${src_path/#\~/$HOME}"
      src_path=$(realpath -m "$src_path")
    else
      [[ "$src" == ~* ]] && src="${src/#\~/$HOME}"
      src_path=$(realpath -m "$src")
    fi

    if [[ ! -e "$src_path" ]]; then
      echo -e "${RED}❌ Source '$src' does not exist${RESET}"
      return 1
    fi

    if [[ "$cmd" == "mv" ]]; then
      if [[ "$dest_is_ssh" == true ]]; then
        rsync -az -e "ssh -i $ssh_key -p $ssh_port" "$src_path" "$dest_rsync_target" && rm -rf "$src_path" && \
          echo -e "${GREEN}✅ Moved '$src_path' to '$dest_rsync_target'${RESET}"
      else
        mv "$src_path" "$dest_path/" && echo -e "${GREEN}✅ Moved '$src_path' to '$dest_path/'${RESET}"
      fi
    else
      if [[ "$dest_is_ssh" == true ]]; then
        rsync -az -e "ssh -i $ssh_key -p $ssh_port" "$src_path" "$dest_rsync_target" && \
          echo -e "${GREEN}✅ Copied '$src_path' to '$dest_rsync_target'${RESET}"
      else
        rsync -a --progress "$src_path" "$dest_path/" && echo -e "${GREEN}✅ Copied '$src_path' to '$dest_path/'${RESET}"
      fi
    fi
  done
}
