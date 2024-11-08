#!/usr/bin/env bash
set -e

# command name to installed
name="dust"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/bootandy/dust/releases/download/v1.1.1/dust-v1.1.1-i686-unknown-linux-gnu.tar.gz
  wget -O dust.tar.gz $url
  tar zxvf dust.tar.gz
  mv dust-*/dust dust
  rm -r dust.tar.gz dust-*
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
