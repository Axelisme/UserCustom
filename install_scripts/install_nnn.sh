#!/usr/bin/env bash
set -e

# command name to installed
name="nnn"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/jarun/nnn/releases/download/v5.0/nnn-static-5.0.x86_64.tar.gz
  wget -O nnn.tar.gz $url
  tar zxvf nnn.tar.gz
  mv nnn-static nnn
  rm nnn.tar.gz
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  if [ "$1" != "--quiet" ] && [ "$1" != "-q" ]; then
    echo "$name already installed, skipping"
  fi
fi
