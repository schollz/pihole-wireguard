#!/usr/bin/env bash
set -euo pipefail

echo "Updating system packages..."
apt update && apt upgrade -y

echo "Installing required packages..."
apt install -y zsh git curl wget qrencode

echo "Installing Oh-My-Zsh (unattended)..."
CALLING_USER="${SUDO_USER:-root}"
CALLING_USER_HOME=$(eval echo "~${CALLING_USER}")

if [[ ! -d "${CALLING_USER_HOME}/.oh-my-zsh" ]]; then
    export RUNZSH=no
    export CHSH=no
    su - "${CALLING_USER}" -c 'export RUNZSH=no CHSH=no; sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"'
else
    echo "Oh-My-Zsh already installed, skipping."
fi

echo "Setting zsh as default shell for ${CALLING_USER}..."
chsh -s "$(which zsh)" "${CALLING_USER}"

echo "Configuring .zshrc..."
cat > "${CALLING_USER_HOME}/.zshrc" << 'ZSHRC'
export ZSH="$HOME/.oh-my-zsh"

ZSH_THEME="robbyrussell"

plugins=(git)

source $ZSH/oh-my-zsh.sh

export EDITOR='vim'
export LANG=en_US.UTF-8
ZSHRC

chown "${CALLING_USER}:${CALLING_USER}" "${CALLING_USER_HOME}/.zshrc"

echo "System setup complete."
