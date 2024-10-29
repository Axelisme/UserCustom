#!/usr/bin/env bash
set -e

# command name to installed
name="oh-my-posh"

install_function() {
  executable=$HOME/.local/bin/oh-my-posh
  url=https://github.com/JanDeDobbeleer/oh-my-posh/releases/latest/download/posh-linux-amd64

  wget -O $executable $url
  chmod +x $executable
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
