#!/usr/bin/env bash

# command name to installed
name="paru"

# main function to install the command
install_function() {
  cd /tmp

  sudo pacman -S --needed base-devel
  git clone https://aur.archlinux.org/paru.git
  cd paru
  makepkg -si
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function
  echo "done"
else
  echo "$name already installed, skipping"
fi
