#!/usr/bin/env bash

anc_handle_set() {
  local BOLD="\033[1m"
  local RESET="\033[0m"
  local RED="\033[0;31m"
  local GREEN="\033[0;32m"
  local YELLOW="\033[0;33m"
  local BLUE="\033[1;34m"
  local CYAN="\033[1;36m"

  local name="${1:-default}"
  local path="$(pwd)"
  local meta_file="$ANCHOR_DIR/$name"

  local is_git=false
  local git_info="{}"
  local docker_info="{}"

  # Detect Git repo
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    is_git=true

    local git_root
    git_root=$(git rev-parse --show-toplevel)

    local git_branch
    git_branch=$(git rev-parse --abbrev-ref HEAD)

    local branch_list
    branch_list=$(git for-each-ref --format='%(refname:short)' refs/heads | jq -R . | jq -s .)

    local tag_list
    tag_list=$(git tag | jq -R . | jq -s .)

    local remote_json="[]"
    if git remote >/dev/null; then
      remote_json=$(git remote -v | awk '{print $1,$2}' | sort -u | jq -Rn '
        [inputs | split(" ") | {name: .[0], url: .[1]}]')
    fi

    local commit_hash commit_author commit_date commit_msg
    commit_hash=$(git log -1 --pretty=format:"%H")
    commit_author=$(git log -1 --pretty=format:"%an")
    commit_date=$(git log -1 --pretty=format:"%ad")
    commit_msg=$(git log -1 --pretty=format:"%s")

    local is_dirty=false
    if [[ -n "$(git status --porcelain)" ]]; then
      is_dirty=true
    fi

    git_info=$(jq -n \
      --arg root "$git_root" \
      --arg branch "$git_branch" \
      --argjson branches "$branch_list" \
      --argjson tags "$tag_list" \
      --argjson remotes "$remote_json" \
      --arg commit "$commit_hash" \
      --arg author "$commit_author" \
      --arg date "$commit_date" \
      --arg message "$commit_msg" \
      --argjson dirty "$is_dirty" \
      '{
        root: $root,
        branch: $branch,
        branches: $branches,
        tags: $tags,
        remotes: $remotes,
        commit: {
          hash: $commit,
          author: $author,
          date: $date,
          message: $message
        },
        is_dirty: $dirty
      }')
  fi

  # Detect Docker (simple heuristic)
  if [[ -f "Dockerfile" || -f "docker-compose.yml" || -f "docker-compose.yaml" ]]; then
    docker_info='{"active": true}'
  fi

  # Compose final JSON
  jq -n \
    --arg path "$path" \
    --argjson git "$git_info" \
    --argjson docker "$docker_info" \
    '{ path: $path, type: "local", git: $git, docker: $docker }' > "$meta_file"

  echo -e "${CYAN}⚓ Anchor '${BOLD}$name${RESET}${CYAN}' set to: ${GREEN}$path${RESET}"
  if [[ "$is_git" == true ]]; then
    echo -e "${BLUE}🔍 Git repository detected:${RESET}"
    echo -e "  ${CYAN}Branch:${RESET} $git_branch"
    echo -e "  ${CYAN}Root:${RESET} $git_root"
    echo -e "  ${CYAN}Remotes:${RESET} $(echo "$remote_json" | jq -r '.[] | "\(.name): \(.url)"')"
    echo -e "  ${CYAN}Last commit:${RESET} $commit_msg"
    [[ "$is_dirty" == true ]] && echo -e "  ${RED}⚠️ Working directory has uncommitted changes${RESET}"
  fi

  return 0
}

