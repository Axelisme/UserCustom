#!/usr/bin/env bash
set -e

# command name to installed
name="fzf"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/junegunn/fzf/releases/download/v0.55.0/fzf-0.55.0-linux_amd64.tar.gz
  wget -O fzf.tar.gz $url
  tar zxvf fzf.tar.gz fzf
  rm fzf.tar.gz
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
