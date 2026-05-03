#!/usr/bin/env bash
set -e

# command name to installed
name="dank-material-shell"
command_name="dms"

# main function to install the command
install_function() {
  cd /tmp
  curl -fsSL https://install.danklinux.com | sh
}

# wrapper to install the command
if ! command -v $command_name &>/dev/null; then
  install_function
  echo "installing $name...done"
else
  if [ "$1" != "--quiet" ] && [ "$1" != "-q" ]; then
    echo "$name already installed, skipping"
  fi
fi
