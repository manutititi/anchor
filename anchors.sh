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

    meta)
      local anchor="$2"
      shift 2

      if [[ -z "$anchor" || "$#" -eq 0 ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc meta <anchor> key=value [key=value ...]"
        return 1
      fi

      if [[ ! -f "$anchor_dir/$anchor" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi

      local meta_file="$anchor_dir/$anchor.meta"
      touch "$meta_file"

      for pair in "$@"; do
        local key="${pair%%=*}"
        local value="${pair#*=}"
        if grep -q "^$key=" "$meta_file"; then
          sed -i "s/^$key=.*/$key=$value/" "$meta_file"
        else
          echo "$key=$value" >> "$meta_file"
        fi
      done

      echo -e "${GREEN}✅ Metadata updated for anchor '${BOLD}$anchor${RESET}${GREEN}'${RESET}"
      ;;

    show)
      local anchor="$2"
      if [[ -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc show <anchor>"
        return 1
      fi
      if [[ ! -f "$anchor_dir/$anchor" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi
      local path note_file meta_file
      path="$(cat "$anchor_dir/$anchor")"
      note_file="$notes_dir/$anchor.note"
      meta_file="$anchor_dir/$anchor.meta"

      echo -e "${CYAN}🔍 Anchor: ${BOLD}$anchor${RESET}"
      echo -e "  ${BLUE}📁 Path:${RESET} $path"

      if [[ -f "$note_file" ]]; then
        echo -e "  ${YELLOW}📝 Note:${RESET} $(< "$note_file")"
      fi

      if [[ -f "$meta_file" ]]; then
        echo -e "  ${GREEN}🧩 Metadata:${RESET}"
        while IFS='=' read -r key value; do
          echo -e "    ${BOLD}$key${RESET} = $value"
        done < "$meta_file"
      fi
      ;;

    run)
      shift
      if [[ "$1" == --filter ]]; then
        local filter="$2"
        local key="${filter%%=*}"
        local value="${filter#*=}"
        shift 2
        local cmd="$*"

        if [[ -z "$key" || -z "$value" || -z "$cmd" ]]; then
          echo -e "${YELLOW}Usage:${RESET} anc run --filter key=value <command>"
          return 1
        fi

        for file in "$anchor_dir"/*; do
          [[ -f "$file" && "$(basename "$file")" != *.note && "$(basename "$file")" != *.meta ]] || continue
          local name="$(basename "$file")"
          local meta_file="$anchor_dir/$name.meta"
          if [[ -f "$meta_file" ]] && grep -q "^$key=$value" "$meta_file"; then
            local path
            path="$(cat "$file")"
            echo -e "${CYAN}⚓ Running in '$name' → $path:${RESET}"
            (cd "$path" && eval "$cmd")
          fi
        done
      else
        local anchor="$1"
        shift
        local cmd="$*"
        if [[ -z "$anchor" || -z "$cmd" ]]; then
          echo -e "${YELLOW}Usage:${RESET} anc run <anchor> <command>"
          return 1
        fi
        if [[ ! -f "$anchor_dir/$anchor" ]]; then
          echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
          return 1
        fi
        local path
        path="$(cat "$anchor_dir/$anchor")"
        echo -e "${CYAN}⚓ Running in '$anchor' → $path:${RESET}"
        (cd "$path" && eval "$cmd")
      fi
      ;;


    
    
    
    ls)
      shift
      local filter_key filter_value
      if [[ "$1" == --filter && "$2" == *=* ]]; then
        filter_key="${2%%=*}"
        filter_value="${2#*=}"
        shift 2
      fi

      echo -e "${BLUE}📌 Available anchors:${RESET}"

      local found=0
      local max_name_len=0

      # Cálculo de longitud máxima para formato
      for file in "$anchor_dir"/*; do
        local name
        name="$(basename "$file")"
        [[ "$name" == *.note || "$name" == *.meta ]] && continue

        # Filtro (solo para cálculo de largo)
        if [[ -n "$filter_key" ]]; then
          local meta_file="$anchor_dir/$name.meta"
          [[ -f "$meta_file" ]] || continue
          grep -q "^$filter_key=$filter_value" "$meta_file" || continue
        fi

        [[ ${#name} -gt $max_name_len ]] && max_name_len=${#name}
      done

      # Mostrar anchors
      for file in "$anchor_dir"/*; do
        local name path note_file note
        name="$(basename "$file")"
        [[ "$name" == *.note || "$name" == *.meta ]] && continue

        # Filtro activo
        if [[ -n "$filter_key" ]]; then
          local meta_file="$anchor_dir/$name.meta"
          [[ -f "$meta_file" ]] || continue
          grep -q "^$filter_key=$filter_value" "$meta_file" || continue
        fi

        path="$(cat "$file")"
        note_file="$notes_dir/$name.note"
        note=""
        [[ -f "$note_file" ]] && note="# $(< "$note_file")"
        printf "  ${CYAN}⚓ %-*s${RESET} → ${GREEN}%-40s${RESET} ${DIM}%s${RESET}\n" \
          "$max_name_len" "$name" "$path" "$note"
        found=1
      done

      if [[ "$found" -eq 0 ]]; then
        echo -e "  ${YELLOW}(⚠️ no matching anchors found)${RESET}"
      fi

      return 0
      ;;












    del)
      if [[ -z "$2" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc del <name>"
      elif [[ -f "$anchor_dir/$2" ]]; then
        rm "$anchor_dir/$2"
        [[ -f "$notes_dir/$2.note" ]] && rm "$notes_dir/$2.note"
        [[ -f "$anchor_dir/$2.meta" ]] && rm "$anchor_dir/$2.meta"
        echo -e "${RED}🗑️ Anchor '${BOLD}$2${RESET}${RED}' deleted${RESET}"
      else
        echo -e "${RED}⚠️ Anchor '$2' does not exist${RESET}"
      fi
      ;;

    prune)
      echo -e "${YELLOW}🧹 Scanning for dead anchors...${RESET}"
      local count=0
      for file in "$anchor_dir"/*; do
        [[ -f "$file" && "$(basename "$file")" != *.note && "$(basename "$file")" != *.meta ]] || continue
        local name path
        name="$(basename "$file")"
        path="$(cat "$file")"
        if [[ ! -d "$path" ]]; then
          rm "$file"
          [[ -f "$notes_dir/$name.note" ]] && rm "$notes_dir/$name.note"
          [[ -f "$anchor_dir/$name.meta" ]] && rm "$anchor_dir/$name.meta"
          echo -e "${RED}🗑️ Removed dead anchor '$name' → $path${RESET}"
          ((count++))
        fi
      done
      if [[ $count -eq 0 ]]; then
        echo -e "${GREEN}✅ No dead anchors found${RESET}"
      else
        echo -e "${YELLOW}🧹 Pruned $count dead anchor(s)${RESET}"
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
        [[ -f "$anchor_dir/$2.meta" ]] && mv "$anchor_dir/$2.meta" "$anchor_dir/$3.meta"
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
      echo -e "  anc set [name]              - ⚓ Set anchor (default if no name)"
      echo -e "  anc <name>                  - ⚓ Go to the specified anchor"
      echo -e "  anc <name> ls               - 📂 List contents of anchor directory"
      echo -e "  anc <name> tree             - 🌲 Tree view of anchor directory"
      echo -e "  anc                         - ⚓ Go to the 'default' anchor"
      echo -e "  anc ls                      - 📌 List all anchors with notes"
      echo -e "  anc show <anchor>           - 🔍 Show metadata and info"
      echo
      echo -e "${CYAN}🛠️  Management:${RESET}"
      echo -e "  anc del <name>              - 🗑️ Delete the specified anchor"
      echo -e "  anc prune                   - 🧹 Delete anchors pointing to missing directories"
      echo -e "  anc rename <old> <new>      - 🔄 Rename an anchor"
      echo -e "  anc note <name> [message]   - 📝 Add or update note for an anchor"
      echo -e "  anc meta <name> k=v [...]   - 🧩 Set metadata key=value pairs"
      echo
      echo -e "${CYAN}▶️  Commands:${RESET}"
      echo -e "  anc run <anchor> <cmd>      - ▶️ Run a command in the anchor directory"
      echo -e "  anc run --filter k=v <cmd>  - 🔍 Run command in anchors matching metadata"
      echo
      echo -e "${CYAN}📂 File Operations:${RESET}"
      echo -e "  anc cp <file> <anchor>/path - 📁 Copy file to anchor subpath"
      echo -e "  anc mv <file> <anchor>/path - 🚚 Move file to anchor subpath"
      ;;

    *)
      local target="$1"
      local second_arg="$2"
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

