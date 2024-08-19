#!/usr/bin/env bash

# command name to installed
name="fd"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/sharkdp/fd/releases/download/v10.1.0/fd-v10.1.0-x86_64-unknown-linux-gnu.tar.gz
  wget -O fd.tar.gz $url
  tar zxvf fd.tar.gz
  mv fd-v10.1.0-*/fd fd
  rm -r fd.tar.gz fd-v10.1.0-*
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
