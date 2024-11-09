#!/usr/bin/env bash
set -e

# command name to installed
name="oh-my-posh"

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

install_function() {
  mkdir -p ~/.local/bin
  cd ~/.local/bin

  url=https://github.com/JanDeDobbeleer/oh-my-posh/releases/latest/download/posh-linux-amd64

  wget -O oh-my-posh $url
  chmod +x oh-my-posh
}

# wrapper to install the command
if ! command -v $name &>/dev/null; then
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
