#!/usr/bin/env bash
set -e

NEED_PACKAGE='nix'

if type paru >/dev/null 2>&1; then
  paru -S --needed $NEED_PACKAGE
elif type yay >/dev/null 2>&1; then
  yay -S --needed $NEED_PACKAGE
else
  echo "No aur package manager found"
fi
