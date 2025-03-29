#!/usr/bin/env bash

set -e

ANCHOR_HOME="$HOME/.anchors"
SHELL_CONFIGS=("$HOME/.bashrc" "$HOME/.zshrc")

echo "🧹 Uninstalling Anchor system from: $ANCHOR_HOME"

# Eliminar carpeta
if [[ -d "$ANCHOR_HOME" ]]; then
  rm -rf "$ANCHOR_HOME"
  echo "🗑️ Removed $ANCHOR_HOME"
else
  echo "⚠️ $ANCHOR_HOME not found, skipping removal."
fi

remove_line() {
  local file="$1"
  local line="$2"
  if grep -Fxq "$line" "$file"; then
    sed -i.bak "\|$line|d" "$file"
    echo "✂️ Removed line from $file: $line"
  fi
}

for CONFIG in "${SHELL_CONFIGS[@]}"; do
  if [[ -f "$CONFIG" ]]; then
    remove_line "$CONFIG" 'export ANCHOR_HOME="$HOME/.anchors"'
    remove_line "$CONFIG" 'export ANCHOR_DIR="$ANCHOR_HOME/data"'
    remove_line "$CONFIG" '[[ -f "$ANCHOR_HOME/functions/anchors.sh" ]] && source "$ANCHOR_HOME/functions/anchors.sh"'
    remove_line "$CONFIG" '[[ -f "$ANCHOR_HOME/completions/anc" ]] && source "$ANCHOR_HOME/completions/anc"'
    echo "✅ Cleaned $CONFIG"
  fi
done

echo "✅ Uninstalled!"
echo "🔁 Please reload your shell or run: source ~/.bashrc or ~/.zshrc"

