#!/usr/bin/env bash

set -e

ANCHOR_HOME="$HOME/.anchors"
SRC_DIR="$(pwd)"

echo "📦 Installing Anchor system to: $ANCHOR_HOME"

# Crear estructura
mkdir -p "$ANCHOR_HOME/functions"
mkdir -p "$ANCHOR_HOME/completions"
mkdir -p "$ANCHOR_HOME/data"

# Copiar archivos
cp "$SRC_DIR/anchors.sh" "$ANCHOR_HOME/functions/anchors.sh"
cp "$SRC_DIR/anc"         "$ANCHOR_HOME/completions/anc"

# Asegurar líneas en .bashrc
BASHRC="$HOME/.bashrc"

add_if_missing() {
  local line="$1"
  grep -Fxq "$line" "$BASHRC" || echo "$line" >> "$BASHRC"
}

add_if_missing 'export ANCHOR_HOME="$HOME/.anchors"'
add_if_missing 'export ANCHOR_DIR="$ANCHOR_HOME/data"'
add_if_missing '[[ -f "$ANCHOR_HOME/functions/anchors.sh" ]] && source "$ANCHOR_HOME/functions/anchors.sh"'
add_if_missing '[[ -f "$ANCHOR_HOME/completions/anc" ]] && source "$ANCHOR_HOME/completions/anc"'

echo "✅ Installed!"
echo "🔁 Please reload your shell or run: source ~/.bashrc"
echo "🚀 Try: anc set test && anc ls"

