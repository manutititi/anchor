anc() {
  # 🎨 Color definitions
  local BOLD="\033[1m"
  local DIM="\033[2m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"
  local CYAN="\033[1;36m"
  local GRAY="\033[0;37m"

  local anchor_dir="${ANCHOR_DIR:-"$HOME/.anchors"}"
  local notes_dir="$anchor_dir/.notes"
  mkdir -p "$anchor_dir" "$notes_dir"

  case "$1" in
    set)
      local name="${2:-default}"
      echo "$(pwd)" > "$anchor_dir/$name"
      echo -e "${CYAN}⚓ Anchor '${BOLD}$name${RESET}${CYAN}' set to: ${GREEN}$(pwd)${RESET}"
      ;;

    note)
      if [[ -z "$2" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc note <anchor> [message]"
        return 1
      fi
      local anchor="$2"
      local msg="${*:3}"
      if [[ ! -f "$anchor_dir/$anchor" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' does not exist${RESET}"
        return 1
      fi
      echo "$msg" > "$notes_dir/$anchor.note"
      echo -e "${BLUE}📝 Note set for anchor '${BOLD}$anchor${RESET}${BLUE}'${RESET}"
      ;;

    ls)
      echo -e "${BLUE}📌 Available anchors:${RESET}"
      if compgen -G "$anchor_dir/*" > /dev/null; then
        local max_name_len=0
        for file in "$anchor_dir"/*; do
          local name
          name="$(basename "$file")"
          [[ ${#name} -gt $max_name_len ]] && max_name_len=${#name}
        done

        # Mostrar primero el anchor 'default'
        if [[ -f "$anchor_dir/default" ]]; then
          local path note_file note
          path="$(cat "$anchor_dir/default")"
          note_file="$notes_dir/default.note"
          note=""
          [[ -f "$note_file" ]] && note="# $(< "$note_file")"
          printf "  ${CYAN}⚓ %-*s${RESET} → ${GREEN}%-40s${RESET} ${DIM}%s${RESET}\n" \
            "$max_name_len" "default" "$path" "$note"
        fi

        # Mostrar el resto ordenado por fecha (más reciente primero), excluyendo 'default'
        find "$anchor_dir" -type f ! -name "default" ! -name "*.note" -printf "%T@ %p\n" \
          | sort -nr \
          | awk '{print $2}' \
          | while read -r file; do
              local name path note_file note
              name="$(basename "$file")"
              path="$(cat "$file")"
              note_file="$notes_dir/$name.note"
              note=""
              [[ -f "$note_file" ]] && note="# $(< "$note_file")"
              printf "  ${CYAN}⚓ %-*s${RESET} → ${GREEN}%-40s${RESET} ${DIM}%s${RESET}\n" \
                "$max_name_len" "$name" "$path" "$note"
            done
      else
        echo -e "  ${YELLOW}(⚠️ no anchors found)${RESET}"
      fi
      ;;

    del)
      if [[ -z "$2" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc del <name>"
      elif [[ -f "$anchor_dir/$2" ]]; then
        rm "$anchor_dir/$2"
        [[ -f "$notes_dir/$2.note" ]] && rm "$notes_dir/$2.note"
        echo -e "${RED}🗑️ Anchor '${BOLD}$2${RESET}${RED}' deleted${RESET}"
      else
        echo -e "${RED}⚠️ Anchor '$2' does not exist${RESET}"
      fi
      ;;

    prune)
      read -p "$(echo -e "${RED}⚠️ Are you sure you want to delete ALL anchors? [y/N]: ${RESET}")" confirm
      if [[ "$confirm" =~ ^([Yy]|[Yy][Ee][Ss])$ ]]; then
        rm -f "$anchor_dir"/*
        rm -f "$notes_dir"/*.note
        echo -e "${YELLOW}🧹 All anchors deleted${RESET}"
      else
        echo -e "${DIM}Operation cancelled${RESET}"
      fi
      ;;

    rename)
      if [[ -z "$2" || -z "$3" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc rename <old> <new>"
      elif [[ ! -f "$anchor_dir/$2" ]]; then
        echo -e "${RED}⚠️ Anchor '$2' does not exist${RESET}"
      else
        mv "$anchor_dir/$2" "$anchor_dir/$3"
        [[ -f "$notes_dir/$2.note" ]] && mv "$notes_dir/$2.note" "$notes_dir/$3.note"
        echo -e "${CYAN}🔄 Anchor '${BOLD}$2${RESET}${CYAN}' renamed to '${BOLD}$3${RESET}${CYAN}'${RESET}"
      fi
      ;;

    cp|mv)
      local cmd="$1"
      local file="$2"
      local anchor_path="$3"
      if [[ -z "$file" || -z "$anchor_path" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc $cmd <file> <anchor>/path"
        return 1
      fi
      if [[ ! -f "$file" ]]; then
        echo -e "${RED}❌ File '$file' does not exist${RESET}"
        return 1
      fi
      local anchor="${anchor_path%%/*}"
      local subpath="${anchor_path#*/}"
      if [[ ! -f "$anchor_dir/$anchor" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi
      local dest_dir
      dest_dir="$(cat "$anchor_dir/$anchor")"
      if [[ "$subpath" != "$anchor_path" ]]; then
        dest_dir="$dest_dir/$subpath"
        mkdir -p "$(dirname "$dest_dir")"
      fi
      $cmd "$file" "$dest_dir" && echo -e "${GREEN}✅ ${cmd^}ed '$file' to '$dest_dir'${RESET}"
      ;;

    help)
      echo -e "${BOLD}📖 anc - Simple anchor system for directories and files${RESET}\n"
      echo -e "${CYAN}🎯 Navigation:${RESET}"
      echo -e "  anc set [name]            - ⚓ Set anchor (default if no name)"
      echo -e "  anc <name>                - ⚓ Go to the specified anchor"
      echo -e "  anc <name> ls             - 📂 List contents of anchor directory"
      echo -e "  anc <name> tree           - 🌲 Tree view of anchor directory"
      echo -e "  anc                       - ⚓ Go to the 'default' anchor"
      echo -e "  anc ls                    - 📌 List all anchors with notes"
      echo
      echo -e "${CYAN}🛠️  Management:${RESET}"
      echo -e "  anc del <name>            - 🗑️ Delete the specified anchor"
      echo -e "  anc prune                 - 🧹 Delete all anchors"
      echo -e "  anc rename <old> <new>    - 🔄 Rename an anchor"
      echo -e "  anc note <name> [message] - 📝 Add or update note for an anchor"
      echo
      echo -e "${CYAN}📂 File Operations:${RESET}"
      echo -e "  anc cp <file> <anchor>/path - 📁 Copy file to anchor subpath"
      echo -e "  anc mv <file> <anchor>/path - 🚚 Move file to anchor subpath"
      ;;

    *)
      local target="$1"
      local second_arg="$2"

      # Ir al anchor 'default' si no se pasa ninguno
      [[ -z "$target" ]] && target="default"

      if [[ -f "$anchor_dir/$target" ]]; then
        local path
        path="$(cat "$anchor_dir/$target")"

        if [[ ! -d "$path" ]]; then
          echo -e "${RED}❌ Anchor '$target' points to non-existent directory: $path${RESET}"
          return 1
        fi

        case "$second_arg" in
          ls)
            echo -e "${BLUE}📂 Listing contents of '${BOLD}$target${RESET}${BLUE}' ($path):${RESET}"
            ls -la "$path"
            ;;
          tree)
            echo -e "${BLUE}🌲 Tree view of '${BOLD}$target${RESET}${BLUE}' ($path):${RESET}"
            if command -v tree >/dev/null 2>&1; then
              tree "$path"
            else
              echo -e "${YELLOW}⚠️ 'tree' command not found. Please install it first.${RESET}"
            fi
            ;;
          *)
            cd "$path" || {
              echo -e "${RED}❌ Failed to access anchor '$target'${RESET}"
              return 1
            }
            ;;
        esac
      else
        echo -e "${RED}⚠️ Anchor '$target' not found${RESET}"
      fi
      ;;
  esac
}

