#!/usr/bin/env bash
set -e

# command name to installed
name="lazygit"

# parse arguments
while [ "$1" != "" ]; do
  case $1 in
  -f | --force)
    force_install=true
    ;;
  -q | --quiet)
    quiet=true
    ;;
  *)
    echo "invalid argument: $1"
    exit 1
    ;;
  esac
  shift
done

# main function to install the command
install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  version=0.45.2
  url=https://github.com/jesseduffield/lazygit/releases/download/v${version}/lazygit_${version}_Linux_x86_64.tar.gz
  wget -O lazygit.tar.gz $url
  tar zxvf lazygit.tar.gz lazygit
  rm lazygit.tar.gz
}

# wrapper to install the command
if ! version_checker; then
  echo -n "installing $name..."
  install_function >/dev/null
  echo "done"
elif [ "$force_install" = true ]; then
  echo -n "$name already installed, force re-installing..."
  install_function >/dev/null
  echo "done"
else
  if [ "$quiet" != true ]; then
    echo "$name already installed, skipping"
  fi
fi
