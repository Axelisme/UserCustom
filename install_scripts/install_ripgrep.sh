#!/usr/bin/env bash

# command name to installed
name="rg"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  wget -O ripgrep.tar.gz https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/ripgrep-14.1.0-x86_64-unknown-linux-musl.tar.gz
  tar zxvf ripgrep.tar.gz
  mv ripgrep-14.1.0-*/rg rg
  rm -r ripgrep.tar.gz ripgrep-14.1.0-*
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
