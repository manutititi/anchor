#!/usr/bin/env bash

set -e

ANCHOR_HOME="$HOME/.anchors"
SRC_DIR="$(pwd)"

echo "📦 Installing Anchor system to: $ANCHOR_HOME"

# Crear estructura de directorios
mkdir -p "$ANCHOR_HOME/functions"
mkdir -p "$ANCHOR_HOME/completions"
mkdir -p "$ANCHOR_HOME/data"

# Copiar archivos
cp "$SRC_DIR/functions/anchors.sh" "$ANCHOR_HOME/functions/anchors.sh"
cp "$SRC_DIR/autocompletions/anc" "$ANCHOR_HOME/completions/anc"

# Archivos de configuración a modificar
SHELL_CONFIGS=("$HOME/.bashrc" "$HOME/.zshrc")

add_if_missing() {
  local file="$1"
  local line="$2"
  grep -Fxq "$line" "$file" || echo "$line" >> "$file"
}

for CONFIG in "${SHELL_CONFIGS[@]}"; do
  if [[ -f "$CONFIG" ]]; then
    add_if_missing "$CONFIG" 'export ANCHOR_HOME="$HOME/.anchors"'
    add_if_missing "$CONFIG" 'export ANCHOR_DIR="$ANCHOR_HOME/data"'
    add_if_missing "$CONFIG" '[[ -f "$ANCHOR_HOME/functions/anchors.sh" ]] && source "$ANCHOR_HOME/functions/anchors.sh"'
    add_if_missing "$CONFIG" '[[ -f "$ANCHOR_HOME/completions/anc" ]] && source "$ANCHOR_HOME/completions/anc"'
    echo "✅ Updated $CONFIG"
  fi
done

echo "✅ Installed!"
echo "🔁 Please reload your shell or run: source ~/.bashrc or ~/.zshrc"
echo "🚀 Try: anc set test && anc ls"

