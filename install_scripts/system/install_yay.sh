#!/usr/bin/env bash

# command name to installed
name="yay"

# main function to install the command
install_function() {
  cd /tmp

  sudo pacman -S --needed git base-devel
  git clone https://aur.archlinux.org/yay.git
  cd yay
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
