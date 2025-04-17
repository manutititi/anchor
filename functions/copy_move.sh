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

  # Detectar si destino es un anchor
  local dest_anchor="${destination%%/*}"
  local dest_subpath="${destination#*/}"
  [[ "$destination" == "$dest_anchor" ]] && dest_subpath=""

  local dest_meta="$ANCHOR_DIR/$dest_anchor.json"
  local dest_path=""
  if [[ -f "$dest_meta" ]]; then
    dest_path=$(jq -r '.path // empty' "$dest_meta")
    [[ "$dest_path" == ~* ]] && dest_path="${dest_path/#\~/$HOME}"
    dest_path=$(realpath -m "$dest_path")
    [[ -n "$dest_subpath" ]] && dest_path="$dest_path/$dest_subpath"
  else
    [[ "$destination" == ~* ]] && destination="${destination/#\~/$HOME}"
    dest_path=$(realpath -m "$destination")
  fi

  mkdir -p "$dest_path" || {
    echo -e "${RED}❌ Failed to create destination path: $dest_path${RESET}"
    return 1
  }

  for src in "${sources[@]}"; do
    # Si viene en formato anchor/*
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
          mv "$matched" "$dest_path/" && echo -e "${GREEN}✅ Moved '$matched' to '$dest_path/'${RESET}"
        else
          rsync -a --progress "$matched" "$dest_path/" && echo -e "${GREEN}✅ Copied '$matched' to '$dest_path/'${RESET}"
        fi
      done
      continue
    fi

    # Origen es un anchor completo
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
      mv "$src_path" "$dest_path/" && echo -e "${GREEN}✅ Moved '$src_path' to '$dest_path/'${RESET}"
    else
      rsync -a --progress "$src_path" "$dest_path/" && echo -e "${GREEN}✅ Copied '$src_path' to '$dest_path/'${RESET}"
    fi
  done
}
