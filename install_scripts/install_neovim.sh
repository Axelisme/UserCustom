#!/usr/bin/env bash
set -e

# command name to installed
name="nvim"

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/neovim/neovim/releases/download/nightly/nvim-linux64.tar.gz
  wget -O nvim.tar.gz $url
  tar zxvf nvim.tar.gz -C ~/.local --strip-components=1
  rm nvim.tar.gz
}

version_checker() {
  if ! command -v nvim &>/dev/null; then
    return 1
  fi

  # nvim versin must >= v0.9.0
  major_version=$(nvim -v | head -n 1 | cut -d. -f2)
  return $((major_version < 9))
}

# check dependencies installed
src_dir=$(dirname $0)
$src_dir/dependencies/install_fd.sh --quiet
$src_dir/dependencies/install_fzf.sh --quiet
# $src_dir/dependencies/install_magick.sh --quiet # optional
$src_dir/dependencies/install_ripgrep.sh --quiet

# src_dir/install_lazygit.sh --quiet # optional

# wrapper to install the command
if ! version_checker; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
else
  if [ "$1" != "--quiet" ] && [ "$1" != "-q" ]; then
    echo "$name already installed, skipping"
  fi
fi
