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
      local path="$(pwd)"
      local meta_file="$anchor_dir/$name"

      mkdir -p "$anchor_dir"

      jq -n --arg path "$path" '{ path: $path, type: "local"}' > "$meta_file"

      echo -e "${CYAN}⚓ Anchor '${BOLD}$name${RESET}${CYAN}' set to: ${GREEN}$path${RESET}"
      ;;


   
    set-ssh)
      local name="${2:-default}"
      local ssh_url="$3"

      if [[ -z "$ssh_url" || "$ssh_url" != ssh://* ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc set-ssh <name> <ssh://user@host:/remote/path>${RESET}"
        return 1
      fi

      # Parse URL
      local full="${ssh_url#ssh://}"     # remove ssh://
      local user_host="${full%%:*}"      # user@host
      local remote_path="${full#*:}"     # /remote/path
      local user="${user_host%@*}"       # user
      local host="${user_host#*@}"       # host

      if [[ -z "$user" || -z "$host" || -z "$remote_path" ]]; then
        echo -e "${RED}❌ Invalid SSH path format${RESET}"
        return 1
      fi

      echo -e "${BLUE}🔌 Testing SSH connection to ${BOLD}$user_host${RESET}${BLUE}...${RESET}"

      if ssh "$user_host" "test -d '$remote_path'" 2>/dev/null; then
        local meta_file="$anchor_dir/$name"
        jq -n \
          --arg path "ssh://$user_host:$remote_path" \
          --arg user "$user" \
          --arg host "$host" \
          '{ path: $path, type: "remote", user: $user, host: $host }' > "$meta_file"

        echo -e "${CYAN}🌐 Remote anchor '${BOLD}$name${RESET}${CYAN}' set to: ${GREEN}$ssh_url${RESET}"
      else
        echo -e "${RED}❌ Could not connect or directory does not exist: $remote_path${RESET}"
        return 1
      fi
      ;;



    note)
      if [[ -z "$2" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc note <anchor> [message]"
        return 1
      fi

      local anchor="$2"
      local msg="${*:3}"
      local meta_file="$anchor_dir/$anchor"

      if [[ ! -f "$meta_file" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' does not exist${RESET}"
        return 1
      fi

      tmp="$(mktemp)"
      jq --arg note "$msg" '.note = $note' "$meta_file" > "$tmp" && mv "$tmp" "$meta_file"

      echo -e "${BLUE}📝 Note set for anchor '${BOLD}$anchor${RESET}${BLUE}'${RESET}"
      ;;




    meta)
      local anchor="$2"
      shift 2

      if [[ -z "$anchor" || "$#" -eq 0 ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc meta <anchor> key=value [key=value ...]"
        return 1
      fi

      local meta_file="$anchor_dir/$anchor"

      if [[ ! -f "$meta_file" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi

      local jq_expr=""
      for pair in "$@"; do
        local key="${pair%%=*}"
        local value="${pair#*=}"
        jq_expr+=".\"$key\" = \"${value}\" | "
      done

      # Eliminar último ' | ' si existe
      jq_expr="${jq_expr% | }"

      local tmp
      tmp="$(mktemp)"
      jq "$jq_expr" "$meta_file" > "$tmp" && mv "$tmp" "$meta_file"

      echo -e "${GREEN}✅ Metadata updated for anchor '${BOLD}$anchor${RESET}${GREEN}'${RESET}"
      ;;




    ls)
      shift
      local filter_string=""
      local filter_mode=false

      if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
        filter_string="$2"
        filter_mode=true
        shift 2
      fi

      echo -e "${BLUE}📌 Available anchors:${RESET}"
      local found=0

      local files=()
      if [[ "$filter_mode" == true ]]; then
        mapfile -t files < <(filter_anchors "$filter_string")
      else
        for file in "$anchor_dir"/*; do
          [[ -f "$file" ]] && files+=("$(basename "$file")")
        done
      fi

      for name in "${files[@]}"; do
        local meta_file="$anchor_dir/$name"
        local path
        path=$(jq -r '.path // empty' "$meta_file")

        if [[ -n "$path" ]]; then
          printf "  ${CYAN}⚓ %-20s${RESET} → ${GREEN}%s${RESET}\n" "$name" "$path"
          found=1
        fi
      done

      if [[ "$found" -eq 0 ]]; then
        echo -e "  ${YELLOW}(⚠️ no matching anchors found)${RESET}"
      fi
      ;;
        

    show)
      local anchor="$2"

      if [[ -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc show <anchor>"
        return 1
      fi

      local meta_file="$anchor_dir/$anchor"

      if [[ ! -f "$meta_file" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi

      echo -e "${CYAN}🔍 Anchor: ${BOLD}$anchor${RESET}"

      local path note
      path=$(jq -r '.path // empty' "$meta_file")
      note=$(jq -r '.note // empty' "$meta_file")

      echo -e "  ${BLUE}📁 Path:${RESET} $path"

      if [[ -n "$note" ]]; then
        echo -e "  ${YELLOW}📝 Note:${RESET} $note"
      fi

      echo -e "  ${GREEN}🧩 Metadata:${RESET}"
      jq 'to_entries | map(select(.key != "path")) | .[] | "    \(.key) = \(.value)"' "$meta_file" -r
      ;;

    
    
        
        
    run)
      shift
      local filter_string=""
      local mode="single"
      local cmd=""
      local files=()

      if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
        filter_string="$2"
        shift 2
        cmd="$*"

        if [[ -z "$cmd" ]]; then
          echo -e "${YELLOW}Usage:${RESET} anc run -f key=value[,key=value...] <command>"
          return 1
        fi

        mapfile -t files < <(filter_anchors "$filter_string")
        mode="filtered"
      else
        local anchor="$1"
        shift
        cmd="$*"

        if [[ -z "$anchor" || -z "$cmd" ]]; then
          echo -e "${YELLOW}Usage:${RESET} anc run <anchor> <command>"
          return 1
        fi

        if [[ ! -f "$anchor_dir/$anchor" ]]; then
          echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
          return 1
        fi

        files+=("$anchor")
      fi

      for name in "${files[@]}"; do
        local meta_file="$anchor_dir/$name"
        local path
        path=$(jq -r '.path // empty' "$meta_file")

        if [[ -z "$path" ]]; then
          echo -e "${YELLOW}⚠️ Anchor '$name' has no path, skipping${RESET}"
          continue
        fi

        echo -e "${CYAN}⚓ Running in '$name' → $path:${RESET}"

        if [[ "$path" == ssh://* ]]; then
          local user_host="${path#ssh://}"
          user_host="${user_host%%:*}"
          remote_path="${path#*:}"
          ssh "$user_host" -t "cd '$remote_path' && $cmd"
        else
          (cd "$path" && eval "$cmd")
        fi
      done
      ;;
    
    


    del)
      shift
      local files=()

      if [[ ("$1" == "--filter" || "$1" == "-f") && "$2" == *=* ]]; then
        local filter_string="$2"
        shift 2
        mapfile -t files < <(filter_anchors "$filter_string")
      elif [[ -n "$1" ]]; then
        files+=("$1")
      else
        echo -e "${YELLOW}Usage:${RESET} anc del <name>  ${DIM}or${RESET}  anc del -f key=value[,key=value...]"
        return 1
      fi

      if [[ ${#files[@]} -eq 0 ]]; then
        echo -e "${YELLOW}⚠️ No matching anchors found${RESET}"
        return 1
      fi

      echo -e "${RED}🚨 The following anchors will be deleted:${RESET}"
      for name in "${files[@]}"; do
        echo -e "  ${CYAN}⚓ $name${RESET}"
      done

      echo -ne "${YELLOW}❓ Are you sure? (y/N): ${RESET}"
      read -r confirm

      if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${BLUE}❌ Operation cancelled${RESET}"
        return 0
      fi

      for name in "${files[@]}"; do
        local meta_file="$anchor_dir/$name"
        if [[ -f "$meta_file" ]]; then
          rm "$meta_file"
          echo -e "${RED}🗑️ Anchor '${BOLD}$name${RESET}${RED}' deleted${RESET}"
        else
          echo -e "${YELLOW}⚠️ Anchor '$name' not found${RESET}"
        fi
      done
      ;;
    


    prune)
      echo -e "${YELLOW}🧹 Scanning for dead local anchors (type=local)...${RESET}"
      local dead=()

      for file in "$anchor_dir"/*; do
        [[ -f "$file" ]] || continue
        local name="$(basename "$file")"

        local type
        type=$(jq -r '.type // "local"' "$file")

        [[ "$type" != "local" ]] && continue

        local path
        path=$(jq -r '.path // empty' "$file")

        [[ -d "$path" ]] || dead+=("$name")
      done

      if [[ ${#dead[@]} -eq 0 ]]; then
        echo -e "${GREEN}✅ No dead local anchors found${RESET}"
        return 0
      fi

      echo -e "${RED}⚠️ The following local anchors point to non-existent directories:${RESET}"
      for name in "${dead[@]}"; do
        local path
        path=$(jq -r '.path' "$anchor_dir/$name")
        echo -e "  ${CYAN}⚓ $name${RESET} → ${DIM}$path${RESET}"
      done

      echo -ne "${YELLOW}❓ Remove these anchors? (y/N): ${RESET}"
      read -r confirm

    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
      echo -e "${BLUE}❌ Operation cancelled${RESET}"
      return 0
    fi

    for name in "${dead[@]}"; do
      rm "$anchor_dir/$name"
      echo -e "${RED}🗑️ Anchor '${BOLD}$name${RESET}${RED}' deleted${RESET}"
    done
    ;;




    rename)
      local old="$2"
      local new="$3"

      if [[ -z "$old" || -z "$new" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc rename <old> <new>"
        return 1
      fi

      local old_file="$anchor_dir/$old"
      local new_file="$anchor_dir/$new"

      if [[ ! -f "$old_file" ]]; then
        echo -e "${RED}⚠️ Anchor '$old' does not exist${RESET}"
        return 1
      fi

      if [[ -f "$new_file" ]]; then
        echo -e "${RED}⚠️ Anchor '$new' already exists${RESET}"
        return 1
      fi

      mv "$old_file" "$new_file"
      echo -e "${CYAN}🔄 Anchor '${BOLD}$old${RESET}${CYAN}' renamed to '${BOLD}$new${RESET}${CYAN}'${RESET}"
      ;;
    
   
    
    
    cp|mv)
      local cmd="$1"
      local file="$2"
      local anchor="$3"

      if [[ -z "$file" || -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc $cmd <file> <anchor>${RESET}"
        return 1
      fi

      if [[ ! -f "$file" ]]; then
        echo -e "${RED}❌ File '$file' does not exist${RESET}"
        return 1
      fi

      if [[ ! -f "$anchor_dir/$anchor" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi

      local path
      path="$(cat "$anchor_dir/$anchor")"

      if [[ "$path" == ssh://* ]]; then
        # Remote destination
        local path_no_proto="${path#ssh://}"
        local user_host="${path_no_proto%%:*}"
        local remote_path="${path_no_proto#*:}"
        local remote_file="$remote_path/$(basename "$file")"
        echo -e "${BLUE}📡 Sending '$file' to remote anchor '$anchor': $user_host:$remote_file${RESET}"
        if [[ "$cmd" == "cp" ]]; then
          scp "$file" "$user_host:$remote_file"
        else
          scp "$file" "$user_host:$remote_file" && rm "$file"
        fi
      else
        # Local destination
        local dest="$path/$(basename "$file")"
        $cmd "$file" "$dest" && echo -e "${GREEN}✅ ${cmd^}ed '$file' to '$dest'${RESET}"
      fi
      ;;
    
    help)
      echo -e "${BOLD}📖 anc - Simple anchor system for directories and files${RESET}\n"

      echo -e "${CYAN}🎯 Navigation:${RESET}"
      echo -e "  anc                        - ⚓ Go to the 'default' anchor"
      echo -e "  anc <name>                - ⚓ Jump to a specific anchor"
      echo -e "  anc <name> ls             - 📂 List contents of anchor directory"
      echo -e "  anc <name> tree           - 🌲 Tree view of anchor directory"
      echo -e "  anc show <name>           - 🔍 Show path, note, and metadata"
      echo -e "  anc ls [--filter k=v]     - 📌 List all anchors (optionally filtered by metadata)"
      echo

      echo -e "${CYAN}🛠️  Anchor Management:${RESET}"
      echo -e "  anc set [name]            - 📍 Set anchor for current directory"
      echo -e "  anc set-ssh <name> <url>  - 🌐 Set anchor to remote SSH path"
      echo -e "  anc del <name>            - 🗑️ Delete an anchor"
      echo -e "  anc rename <old> <new>    - 🔄 Rename an anchor"
      echo -e "  anc prune                 - 🧹 Remove anchors pointing to non-existent dirs"
      echo -e "  anc note <name> [msg]     - 📝 Add or update note for an anchor"
      echo -e "  anc meta <name> k=v ...   - 🧩 Set metadata (key=value) for an anchor"
      echo

      echo -e "${CYAN}▶️  Execute Commands:${RESET}"
      echo -e "  anc run <name> <cmd>      - 🚀 Run command inside anchor directory"
      echo -e "  anc run --filter k=v <cmd> - 🔎 Run command in anchors matching metadata"
      echo

      echo -e "${CYAN}📂 File Transfer:${RESET}"
      echo -e "  anc cp <file> <anchor>    - 📥 Copy local file to anchor's directory"
      echo -e "  anc mv <file> <anchor>    - 🚚 Move local file to anchor's directory"
      ;;
    



   
    *)
      local target="${1:-default}"
      local second_arg="$2"

      local meta_file="$anchor_dir/$target"

      if [[ -f "$meta_file" ]]; then
        local path
        path=$(jq -r '.path // empty' "$meta_file")

        if [[ -z "$path" ]]; then
          echo -e "${RED}❌ No 'path' found in anchor '${BOLD}$target${RESET}${RED}'${RESET}"
          return 1
        fi

        if [[ "$path" =~ ^ssh://([a-zA-Z0-9._%-]+@[a-zA-Z0-9._%-]+):(.+) ]]; then
          local user_host="${BASH_REMATCH[1]}"
          local remote_path="${BASH_REMATCH[2]}"
          echo -e "${BLUE}🔐 Connecting to remote anchor: ${BOLD}$user_host${RESET}${BLUE} at ${GREEN}$remote_path${RESET}"
          ssh "$user_host" -t "cd '$remote_path' && exec bash"
          return $?
        fi

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
        return 1
      fi
      ;;










     esac
}


filter_anchors() {
  local filter_string="$1"
  local anchor_dir="${ANCHOR_DIR:-"$HOME/.anchors"}"
  declare -A filters

  IFS=',' read -ra pairs <<< "$filter_string"
  for pair in "${pairs[@]}"; do
    local key="${pair%%=*}"
    local value="${pair#*=}"
    filters["$key"]="$value"
  done

  for file in "$anchor_dir"/*; do
    [[ -f "$file" ]] || continue
    local match=true
    for key in "${!filters[@]}"; do
      local val
      val=$(jq -r --arg key "$key" '.[$key] // empty' "$file")
      [[ "$val" != "${filters[$key]}" ]] && match=false && break
    done
    [[ "$match" == true ]] && basename "$file"
  done
}
