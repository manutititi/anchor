#!/usr/bin/env bash

set -e

ANCHOR_HOME="$HOME/.anchors"
SHELL_CONFIGS=("$HOME/.bashrc" "$HOME/.zshrc")

echo "🧹 Uninstalling Anchor system from: $ANCHOR_HOME"

# Eliminar carpeta de instalación
if [[ -d "$ANCHOR_HOME" ]]; then
  rm -rf "$ANCHOR_HOME"
  echo "✅ Removed directory: $ANCHOR_HOME"
else
  echo "ℹ️ Anchor directory not found. Skipping removal."
fi

# Remover líneas de configuración en los shells
remove_line() {
  local file="$1"
  local pattern="$2"
  if [[ -f "$file" ]]; then
    sed -i.bak "/${pattern//\//\\/}/d" "$file"
    rm -f "${file}.bak"
  fi
}

for CONFIG in "${SHELL_CONFIGS[@]}"; do
  if [[ -f "$CONFIG" ]]; then
    remove_line "$CONFIG" 'export ANCHOR_HOME='
    remove_line "$CONFIG" 'export ANCHOR_DIR='
    remove_line "$CONFIG" 'source "\$ANCHOR_HOME/functions/anchors.sh"'
    remove_line "$CONFIG" 'source "\$ANCHOR_HOME/completions/anc"'
    remove_line "$CONFIG" 'for f in "\$ANCHOR_HOME/functions/"\*.sh; do source "\$f"; done'

    echo "🧽 Cleaned $CONFIG"
  fi
done

# Intentar eliminar funciones del entorno actual
unset -f anc 2>/dev/null || true
unset -f anc_* 2>/dev/null || true
hash -r

echo "🧼 Cleared loaded functions from current shell session (if present)"
echo "🗑️ Uninstallation complete!"
echo "🔁 Please reload your shell or run: source ~/.bashrc or ~/.zshrc"

