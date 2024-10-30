#!/usr/bin/env bash
set -e

# if micromamba is not installed, show a warning and exit
if ! type ya >/dev/null 2>&1; then
  echo "yazi could not be found. Please install yazi and try again."
  exit
fi

# install yazi package
ya pack -a yazi-rs/plugins:chmod
ya pack -a KKV9/compress
ya pack -a yazi-rs/plugins:git
ya pack -a Reledia/glow
ya pack -a yazi-rs/plugins:hide-preview

# install yazi theme
ya pack -a BennyOe/onedark
