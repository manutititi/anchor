#!/usr/bin/env bash

anc_enter_anchor() {
  local name="$1"
  local second_arg="$2"
  local meta_file="$ANCHOR_DIR/$name"

  if [[ ! -f "$meta_file" ]]; then
    echo -e "${RED}⚠️ Anchor '$name' not found${RESET}"
    return 1
  fi

  local path
  path=$(jq -r '.path // empty' "$meta_file")

  if [[ -z "$path" ]]; then
    echo -e "${RED}❌ No 'path' found in anchor '${BOLD}$name${RESET}${RED}'${RESET}"
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
    echo -e "${RED}❌ Anchor '$name' points to non-existent directory: $path${RESET}"
    return 1
  fi

  case "$second_arg" in
    ls)
      echo -e "${BLUE}📂 Listing contents of '${BOLD}$name${RESET}${BLUE}' ($path):${RESET}"
      ls -la "$path"
      ;;
    tree)
      echo -e "${BLUE}🌲 Tree view of '${BOLD}$name${RESET}${BLUE}' ($path):${RESET}"
      if command -v tree >/dev/null 2>&1; then
        tree "$path"
      else
        echo -e "${YELLOW}⚠️ 'tree' command not found. Please install it first.${RESET}"
      fi
      ;;
    *)
      cd "$path" || {
        echo -e "${RED}❌ Failed to access anchor '$name'${RESET}"
        return 1
      }

      if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local anchor_branch
        anchor_branch=$(jq -r '.git.branch // empty' "$meta_file")

        if [[ -n "$anchor_branch" ]]; then
          local current_branch
          current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

          if [[ "$current_branch" != "$anchor_branch" ]]; then
            if git show-ref --verify --quiet "refs/heads/$anchor_branch"; then
              echo -e "${CYAN}🔀 Switching to branch '${BOLD}$anchor_branch${RESET}${CYAN}'...${RESET}"
              git switch "$anchor_branch"
            else
              echo -e "${YELLOW}⚠️ Branch '$anchor_branch' not found in repo${RESET}"
            fi
          fi
        fi
      fi
      ;;
  esac
}

