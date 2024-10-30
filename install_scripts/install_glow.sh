#!/usr/bin/env bash
set -e

# command name to installed
name="glow"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/charmbracelet/glow/releases/download/v2.0.0/glow_2.0.0_Linux_x86_64.tar.gz
  wget -O glow.tar.gz $url
  tar zxvf glow.tar.gz
  mv glow_*/glow glow
  rm -r glow.tar.gz glow_*
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
