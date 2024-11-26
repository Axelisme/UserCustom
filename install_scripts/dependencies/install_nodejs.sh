#!/usr/bin/env bash
set -e

# command name to installed
name="node"

# main function to install the command
install_function() {
  mkdir -p ~/.local
  cd ~/.local

  url=https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz
  wget -O node.tar.xz $url
  tar xvf node.tar.xz --strip-components=1
  rm node.tar.xz LICENSE *.md
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
