#!/usr/bin/env bash

# command name to installed
name="nvim"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/neovim/neovim/releases/download/nightly/nvim-linux64.tar.gz
  wget -O nvim.tar.gz $url
  tar zxvf nvim.tar.gz -C ~/.local --strip-components=1
  rm nvim.tar.gz
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
