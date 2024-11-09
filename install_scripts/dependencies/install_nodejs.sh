#!/usr/bin/env bash
set -e

# command name to installed
name="node"

# main function to install the command
install_function() {
  mkdir -p ~/.local
  cd ~/.local

  url=https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz
  wget -O node.tar.gz $url
  tar xJvf node.tar.gz
  mv node-*/bin bin
  mv node-*/lib lib
  mv node-*/share share
  mv node-*/include include
  rm -rf node.tar.gz node-*
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
