#!/usr/bin/env bash
set -e

# command name to installed
name="micromamba"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  echo "$name already installed, skipping"
fi
