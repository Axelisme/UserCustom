#!/usr/bin/env bash
set -e

# command name to installed
name="yazi"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/sxyazi/yazi/releases/download/nightly/yazi-x86_64-unknown-linux-gnu.zip
  wget -O yazi.zip $url
  unzip yazi.zip && mv yazi-* yazi_pkg

  mv yazi_pkg/ya* .

  rm yazi.zip && rm -rf yazi_pkg
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
