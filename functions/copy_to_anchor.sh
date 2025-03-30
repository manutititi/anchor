#!/usr/bin/env bash

anc_handle_cpt() {
  local anchor_dir="$ANCHOR_DIR"
  local from="$1"
  local to="$2"

  if [[ -z "$from" || -z "$to" ]]; then
    echo -e "${YELLOW}Usage:${RESET} anc cpt <from-anchor/relpath> <to-anchor/relpath>${RESET}"
    return 1
  fi

  local src_anchor="${from%%/*}"
  local src_rel="${from#*/}"
  [[ "$src_anchor" == "$from" ]] && src_rel=""

  local dst_anchor="${to%%/*}"
  local dst_rel="${to#*/}"
  [[ "$dst_anchor" == "$to" ]] && dst_rel=""

  local src_meta="$anchor_dir/$src_anchor"
  local dst_meta="$anchor_dir/$dst_anchor"

  if [[ ! -f "$src_meta" ]]; then
    echo -e "${RED}⚠️ Source anchor '$src_anchor' not found${RESET}"
    return 1
  fi

  if [[ ! -f "$dst_meta" && ! -d "$to" ]]; then
    echo -e "${RED}⚠️ Destination '$to' is neither an anchor nor an existing directory${RESET}"
    return 1
  fi

  local src_base dst_base src_type dst_type
  src_base=$(jq -r '.path // empty' "$src_meta")
  src_type=$(jq -r '.type // "local"' "$src_meta")

  if [[ -f "$dst_meta" ]]; then
    dst_base=$(jq -r '.path // empty' "$dst_meta")
    dst_type=$(jq -r '.type // "local"' "$dst_meta")
  else
    dst_base="$to"
    dst_type="local"
  fi

  if [[ -z "$src_base" || -z "$dst_base" ]]; then
    echo -e "${RED}❌ Could not resolve source or destination path${RESET}"
    return 1
  fi

  local dst_path="$dst_base/$dst_rel"
  mkdir -p "$dst_path"

  if [[ "$src_type" == "remote" ]]; then
    local trimmed="${src_base#ssh://}"
    local user_host="${trimmed%%:*}"
    local remote_base="${trimmed#*:}"
    local remote_path

    if [[ -z "$src_rel" ]]; then
      remote_path="$remote_base/"
    else
      remote_path="$remote_base/$src_rel"
    fi

    echo -e "${BLUE}🔍 Listing files in remote '$src_anchor': $user_host:$remote_path${RESET}"
    ssh "$user_host" "ls -1 $remote_path" || {
      echo -e "${RED}❌ Could not list remote files: $user_host:$remote_path${RESET}"
      return 1
    }

    echo -e "${BLUE}📥 Copying from remote '$src_anchor': $user_host:$remote_path → $dst_path${RESET}"
    rsync -avz --progress -e ssh "$user_host:$remote_path" "$dst_path/"
  else
    local src_pattern="$src_base/$src_rel"

    echo -e "${BLUE}📄 Copying from local '$src_anchor': $src_pattern → $dst_path${RESET}"

    shopt -s nullglob
    local matches=($src_pattern)
    shopt -u nullglob

    if [[ ${#matches[@]} -eq 0 ]]; then
      echo -e "${RED}❌ No matching files for '$src_pattern'${RESET}"
      return 1
    fi

    echo -e "${BLUE}🔍 Files to copy:${RESET}"
    for file in "${matches[@]}"; do
      echo "  - $file"
    done

    cp -r "${matches[@]}" "$dst_path"
    echo -e "${GREEN}✅ Copied ${#matches[@]} file(s)${RESET}"
  fi
}

