#!/usr/bin/env bash
set -e

# command name to installed
name="stew"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  version=0.6.0
  url=https://github.com/marwanhawari/stew/releases/download/v${version}/stew-v${version}-linux-amd64.tar.gz
  wget -O stew.tar.gz $url
  tar zxvf stew.tar.gz stew
  rm stew.tar.gz
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
