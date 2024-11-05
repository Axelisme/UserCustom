#!/usr/bin/env bash
set -e

# command name to installed
name="unzip"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://oss.oracle.com/el4/unzip/unzip.tar
  wget -O unzip.tar $url
  tar -xf unzip.tar
  rm -r unzip.tar
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
