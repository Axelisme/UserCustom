#!/usr/bin/env bash

# command name to installed
name="lazygit"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/jesseduffield/lazygit/releases/download/v0.44.1/lazygit_0.44.1_Linux_x86_64.tar.gz
  wget -O lazygit.tar.gz $url
  tar zxvf lazygit.tar.gz lazygit
  rm lazygit.tar.gz
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
