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

# check dependencies installed
src_dir=$(dirname $0)
$src_dir/dependencies/install_fd.sh --quiet
$src_dir/dependencies/install_fzf.sh --quiet
$src_dir/dependencies/install_lsd.sh --quiet
$src_dir/dependencies/install_ohmyposh.sh --quiet
$src_dir/dependencies/install_ripgrep.sh --quiet

# wrapper to install the command
if ! command -v $name &>/dev/null; then
  install_function
  echo "installing $name...done"
else
  if [ "$1" != "--quiet" ] && [ "$1" != "-q" ]; then
    echo "$name already installed, skipping"
  fi
fi
