#!/usr/bin/env bash
set -e

NEED_PACKAGE='unzip xsel nnn git lazygit nodejs advcpmv ripgrep lsd fzf fd oh-my-posh-bin neovim imagemagick yazi'

if type paru >/dev/null 2>&1; then
  paru -S --needed $NEED_PACKAGE
elif type yay >/dev/null 2>&1; then
  yay -S --needed $NEED_PACKAGE
else
  echo "No aur package manager found"
fi

# yazi
ya pack -a yazi-rs/plugins:hide-preview
ya pack -a BennyOe/onedark
