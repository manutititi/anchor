# Root
# Root paths
export ANCHOR_ROOT="${ANCHOR_ROOT:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"}"
export ANCHOR_DIR="${ANCHOR_DIR:-"$ANCHOR_ROOT/data"}"
export ENV_DIR="${ENV_DIR:-"$ANCHOR_ROOT/envs"}"
export URL_DIR="${URL_DIR:-"$ANCHOR_ROOT/urls"}"
PYTHON_BIN="$ANCHOR_ROOT/venv/bin/python"



anc() {
  # Colors
  local BOLD="\033[1m"
  local DIM="\033[2m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"
  local CYAN="\033[1;36m"
  local GRAY="\033[0;37m"

  local anchor_dir="$ANCHOR_DIR"
  mkdir -p "$anchor_dir"

  case "$1" in
    
    
        
    set)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" set "$@"
      ;;




    set-ssh)
      source "${BASH_SOURCE%/*}/set_ssh.sh"
      anc_handle_set_ssh "$2" "$3"
      ;;



    edit)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" edit "$@"
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
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" meta "$@"
      ;;

    


    ls)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" ls "$@"
      ;;

    

            

    show)
     source "${BASH_SOURCE%/*}/show.sh"
     anc_show_anchor "$2"
     ;;
    
    
        
        
        
    run)
      source "${BASH_SOURCE%/*}/run.sh"
      anc_handle_run "$@"
      ;;

 


        
    del)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" del "$@"
      ;;


    
    prune)
      source "${BASH_SOURCE%/*}/prune.sh"
      anc_handle_prune
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
    
     


    url)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" url "$@"
      ;;


    
    
    cp|mv)
     source "${BASH_SOURCE%/*}/copy_move.sh"
     anc_handle_copy_or_move "$@"
     ;;
   


    sail)
      local anchor="$2"

      if [[ -z "$anchor" ]]; then
        echo -e "${YELLOW}Usage:${RESET} anc sail <anchor>${RESET}"
        return 1
      fi

      local base_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
      local anchor_dir="$ANCHOR_DIR"
      local meta_file="$anchor_dir/$anchor"

      if [[ ! -f "$meta_file" ]]; then
        echo -e "${RED}⚠️ Anchor '$anchor' not found${RESET}"
        return 1
      fi

      local old_path
      old_path=$(jq -r '.path // empty' "$meta_file")

      if [[ -z "$old_path" ]]; then
        echo -e "${RED}❌ Anchor '$anchor' has no path${RESET}"
        return 1
      fi

      if [[ "$old_path" =~ ^ssh:// ]]; then
        echo -e "${YELLOW}⚠️ Remote anchors are not supported by 'sail'${RESET}"
        return 1
      fi

      if [[ -d "$old_path" ]]; then
        echo -e "${GREEN}✅ Anchor '$anchor' path is valid: $old_path${RESET}"
        return 0
      fi

      local folder_name
      folder_name="$(basename "$old_path")"

      echo -e "${YELLOW}⚠️ Anchor '$anchor' not found at ${DIM}$old_path${RESET}"
      echo -e "${BLUE}🔍 Searching for '$folder_name' under \$HOME...${RESET}"

      mapfile -t matches < <(find "$HOME" -type d -name "$folder_name" 2>/dev/null)

      if [[ ${#matches[@]} -eq 0 ]]; then
        echo -e "${RED}❌ No alternative location found for '$folder_name'${RESET}"
        return 1
      fi

      echo -e "${CYAN}Select a new location:${RESET}"
      for i in "${!matches[@]}"; do
        printf "  [%d] %s\n" $((i + 1)) "${matches[$i]}"
      done
      printf "  [%d] Cancel\n" $(( ${#matches[@]} + 1 ))

      echo -ne "${YELLOW}❓ Your choice [1-${#matches[@]}]: ${RESET}"
      read -r choice

      if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}❌ Invalid input${RESET}"
        return 1
      fi

      if (( choice < 1 || choice > ${#matches[@]} )); then
        echo -e "${BLUE}❌ Cancelled${RESET}"
        return 0
      fi

      local new_path="${matches[$((choice - 1))]}"

      tmp="$(mktemp)"
      jq --arg new "$new_path" '.path = $new' "$meta_file" > "$tmp" && mv "$tmp" "$meta_file"

      echo -e "${GREEN}✅ Anchor '$anchor' updated to new path: $new_path${RESET}"
      ;;


    bck)
      source "${BASH_SOURCE%/*}/backup.sh"
      anc_handle_backup "${@:2}"
      ;;



    push)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" push "$@"
      ;;


    pull)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" pull "$@"
      ;;

    help)
      source "${BASH_SOURCE%/*}/help.sh"
      anc_handle_help
      ;;    
        


    export)
      shift
      source "${BASH_SOURCE%/*}/export.sh"
      anc_handle_export "$@"
      ;;


    man)
      source "${BASH_SOURCE%/*}/man.sh"
      anc_handle_man
      ;; 

    server)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" server "$@"
      ;;

    ldap)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" ldap "$@"
      ;;

    env)
      shift
      source "${BASH_SOURCE%/*}/env.sh"
      anc_env_apply "$@"
      ;;


    rc)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" rc "$@"
      ;;


    cr)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" cr "$@"
      ;;


    sible)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" sible "$@"
      ;;



    doc)
      shift
      "$PYTHON_BIN" "$ANCHOR_ROOT/core/main.py" doc "$@"
      ;;

        
    *)
     local target="${1:-default}"
     local second_arg="$2"
     source "${BASH_SOURCE%/*}/enter_anchor.sh"
     anc_enter_anchor "$target" "$second_arg"
     ;;



     esac
}


filter_anchors() {
  local filter_string="$1"
  declare -A filters

  IFS=',' read -ra pairs <<< "$filter_string"
  for pair in "${pairs[@]}"; do
    local key="${pair%%=*}"
    local value="${pair#*=}"
    filters["$key"]="$value"
  done

  for file in "$ANCHOR_DIR"/*; do
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
