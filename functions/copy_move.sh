#!/usr/bin/env bash

anc_handle_copy_or_move() {
  local cmd="$1"
  shift

  if [[ "$#" -lt 2 ]]; then
    echo -e "${YELLOW}Usage:${RESET} anc $cmd <file...> <anchor[/subpath]>${RESET}"
    return 1
  fi

  local anchor_path="${@: -1}"
  local sources=("${@:1:$#-1}")

  for file in "${sources[@]}"; do
    if [[ ! -f "$file" && ! -d "$file" ]]; then
      echo -e "${RED}❌ File or directory '$file' does not exist${RESET}"
      return 1
    fi
  done

  local anchor_name subpath
  anchor_name="${anchor_path%%/*}"
  subpath="${anchor_path#*/}"
  [[ "$anchor_path" == "$anchor_name" ]] && subpath=""

  local anchor_dir="$ANCHOR_DIR"
  local meta_file="$anchor_dir/$anchor_name"

  if [[ ! -f "$meta_file" ]]; then
    echo -e "${RED}⚠️ Anchor '$anchor_name' not found${RESET}"
    return 1
  fi

  local path type
  path=$(jq -r '.path // empty' "$meta_file")
  type=$(jq -r '.type // "local"' "$meta_file")

  if [[ -z "$path" ]]; then
    echo -e "${RED}⚠️ Anchor '$anchor_name' has no path${RESET}"
    return 1
  fi

  if [[ "$type" == "remote" ]]; then
    if [[ "$cmd" == "mv" ]]; then
      echo -e "${RED}❌ 'mv' to remote anchors is not allowed. Use 'cp' instead.${RESET}"
      return 1
    fi

    local proto_removed="${path#ssh://}"
    local user_host="${proto_removed%%:*}"
    local remote_path="${proto_removed#*:}"
    [[ -n "$subpath" ]] && remote_path="$remote_path/$subpath"

    echo -e "${BLUE}📡 Sending to remote anchor '$anchor_name': $user_host:$remote_path${RESET}"
    ssh "$user_host" "mkdir -p '$remote_path'" || {
      echo -e "${RED}❌ Failed to create remote directory '$remote_path' on $user_host${RESET}"
      return 1
    }

    scp -r "${sources[@]}" "$user_host:$remote_path"
  else
    local dest="$path"
    [[ -n "$subpath" ]] && dest="$dest/$subpath"
    mkdir -p "$dest"

    for file in "${sources[@]}"; do
      local final_path="$dest/$(basename "$file")"
      if [[ "$cmd" == "mv" ]]; then
        mv "$file" "$final_path" && echo -e "${GREEN}✅ Moved '$file' to '$final_path'${RESET}"
      else
        cp -r "$file" "$final_path" && echo -e "${GREEN}✅ Copied '$file' to '$final_path'${RESET}"
      fi
    done
  fi
}

