#!/usr/bin/env bash

anc_generate_metadata() {
  local path="${1:-$(pwd)}"
  local __resultvar="$2"

  local git_info="{}"
  local docker_info="{}"

  # Git detection
  if git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local git_root git_branch branch_list tag_list remote_json
    local commit_hash commit_author commit_date commit_msg is_dirty

    git_root=$(git -C "$path" rev-parse --show-toplevel)
    git_branch=$(git -C "$path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
    branch_list=$(git -C "$path" for-each-ref --format='%(refname:short)' refs/heads | jq -R . | jq -s .)
    tag_list=$(git -C "$path" tag | jq -R . | jq -s .)

    remote_json=$(git -C "$path" remote -v | awk '{print $1,$2}' | sort -u | jq -Rn '
      [inputs | split(" ") | {name: .[0], url: .[1]}]')

    if git -C "$path" show-ref --quiet; then
      commit_hash=$(git -C "$path" log -1 --pretty=format:"%H")
      commit_author=$(git -C "$path" log -1 --pretty=format:"%an")
      commit_date=$(git -C "$path" log -1 --pretty=format:"%ad")
      commit_msg=$(git -C "$path" log -1 --pretty=format:"%s")
    fi

    is_dirty=false
    if [[ -n "$(git -C "$path" status --porcelain)" ]]; then
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
      '
      {
        root: $root,
        branch: $branch,
        branches: $branches,
        tags: $tags,
        remotes: $remotes,
        is_dirty: $dirty
      }
      + ( $commit != "" 
          | if . then {
              commit: {
                hash: $commit,
                author: $author,
                date: $date,
                message: $message
              }
            } else {} end )')
  fi

  # Docker Compose detection
  local compose_file=""
  if [[ -f "$path/docker-compose.yml" ]]; then
    compose_file="$path/docker-compose.yml"
  elif [[ -f "$path/docker-compose.yaml" ]]; then
    compose_file="$path/docker-compose.yaml"
  fi

  if [[ -n "$compose_file" && -x "$(command -v yq)" ]]; then
    local service_json
    service_json=$(yq eval -o=json '.services // {}' "$compose_file" | jq 'to_entries | map({
      name: .key,
      image: (.value.image // null),
      ports: (.value.ports // []),
      volumes: (.value.volumes // [])
    })')

    docker_info=$(jq -n \
      --arg compose_file "$compose_file" \
      --argjson services "$service_json" \
      '{ active: true, compose_file: $compose_file, services: $services }')
  elif [[ -n "$compose_file" ]]; then
    docker_info=$(jq -n '{ active: true, compose_file: "'"$compose_file"'", services: [] }')
  fi

  local json
  json=$(jq -n \
    --arg path "$path" \
    --argjson git "$git_info" \
    --argjson docker "$docker_info" \
    '{ path: $path, type: "local", git: $git, docker: $docker }')

  # Guardar en la variable de salida
  printf -v "$__resultvar" '%s' "$json"
}

