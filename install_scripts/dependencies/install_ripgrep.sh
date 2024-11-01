#!/usr/bin/env bash
set -e

# command name to installed
name="rg"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  wget -O ripgrep.tar.gz https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz
  tar zxvf ripgrep.tar.gz
  mv ripgrep-*/rg rg
  rm -r ripgrep.tar.gz ripgrep-*
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
