#!/usr/bin/env bash

NEED_PACKAGE='xsel nnn git lazygit advcpmv ripgrep lsd fzf fd oh-my-posh-bin neovim zinit'

if type paru >/dev/null 2>&1; then
  paru -S --needed $NEED_PACKAGE
elif type yay >/dev/null 2>&1; then
  yay -S --needed $NEED_PACKAGE
else
  echo "No aur package manager found"
fi
