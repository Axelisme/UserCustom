#!/usr/bin/env bash

# command name to installed
name="lsd"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/lsd-rs/lsd/releases/download/v1.1.5/lsd-v1.1.5-x86_64-unknown-linux-gnu.tar.gz
  wget -O lsd.tar.gz $url
  tar zxvf lsd.tar.gz
  mv lsd-*/lsd lsd
  rm -r lsd.tar.gz lsd-*
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
