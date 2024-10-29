#!/usr/bin/env bash
set -e

# command name to installed
name="zsh"

# main function to install the command
install_function() {
  cd /tmp

  url=https://raw.githubusercontent.com/romkatv/zsh-bin/master/install
  wget -O zsh_installer $url
  bash ./zsh_installer
  rm zsh_installer
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  install_function
  echo "installing $name...done"
else
  echo "$name already installed, skipping"
fi
