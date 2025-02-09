#!/usr/bin/env bash
set -e

# command name to installed
name="nix-portable"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/DavHau/nix-portable/releases/latest/download/nix-portable-$(uname -m)
  curl -L $url >./nix-portable
  chmod +x ./nix-portable
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
