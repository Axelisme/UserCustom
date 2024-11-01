#!/usr/bin/env bash
set -e

# command name to installed
name="magick"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://imagemagick.org/archive/binaries/magick
  wget -O magick $url

  # try to execute the command, if it fails, remove the file and raise an error
  if ! ./magick -version &>/dev/null; then
    rm magick
    echo "failed to install $name"
    exit 1
  fi
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
