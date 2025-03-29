#!/usr/bin/env bash

set -e

ANCHOR_HOME="$HOME/.anchors"
BASHRC="$HOME/.bashrc"

echo "🧹 Uninstalling Anchor system from: $ANCHOR_HOME"

# Eliminar carpeta
if [[ -d "$ANCHOR_HOME" ]]; then
  rm -rf "$ANCHOR_HOME"
  echo "🗑️ Removed $ANCHOR_HOME"
else
  echo "⚠️ $ANCHOR_HOME not found, skipping removal."
fi

# Eliminar líneas del .bashrc
remove_line() {
  local line="$1"
  if grep -Fxq "$line" "$BASHRC"; then
    sed -i.bak "\|$line|d" "$BASHRC"
    echo "✂️ Removed line from .bashrc: $line"
  fi
}

remove_line 'export ANCHOR_HOME="$HOME/.anchors"'
remove_line 'export ANCHOR_DIR="$ANCHOR_HOME/data"'
remove_line '[[ -f "$ANCHOR_HOME/functions/anchors.sh" ]] && source "$ANCHOR_HOME/functions/anchors.sh"'
remove_line '[[ -f "$ANCHOR_HOME/completions/anc" ]] && source "$ANCHOR_HOME/completions/anc"'

echo "✅ Uninstalled!"
echo "🔁 Please reload your shell or run: source ~/.bashrc"

