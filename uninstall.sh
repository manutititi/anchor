#!/usr/bin/env bash
set -e

ANCHOR_HOME="$HOME/.anchors"
RESET="\033[0m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"

echo -e "${YELLOW}🧹 Uninstalling Anchor from $ANCHOR_HOME...${RESET}"

# Eliminar el directorio de instalación
if [[ -d "$ANCHOR_HOME" ]]; then
  rm -rf "$ANCHOR_HOME"
  echo -e "${GREEN}✅ Removed $ANCHOR_HOME${RESET}"
else
  echo -e "${YELLOW}⚠️ Directory $ANCHOR_HOME not found.${RESET}"
fi

# Limpiar los archivos de configuración del shell
clean_shell_config() {
  local config="$1"
  if [[ ! -f "$config" ]]; then return; fi

  echo -e "${BLUE}🧽 Cleaning $config...${RESET}"
  sed -i '/export ANCHOR_HOME=.*\/.anchors/d' "$config"
  sed -i '/export ANCHOR_DIR=.*\/.anchors\/data/d' "$config"
  sed -i '/for f in "\$ANCHOR_HOME\/functions\//d' "$config"
  sed -i '/source "\$f"/d' "$config"
  sed -i '/source "\$ANCHOR_HOME\/completions\/anc"/d' "$config"
  sed -i '/PATH="\$ANCHOR_HOME\/core:\$PATH"/d' "$config"
  sed -i '/source "\$ANCHOR_HOME\/venv\/bin\/activate"/d' "$config"
  sed -i '/source "\$HOME\/.anchors\/venv\/bin\/activate"/d' "$config"
}

clean_shell_config "$HOME/.bashrc"
clean_shell_config "$HOME/.zshrc"

echo -e "\n${GREEN}✅ Uninstallation complete.${RESET}"
echo -e "${YELLOW}🔁 Please restart your shell or run: source ~/.bashrc${RESET}"

