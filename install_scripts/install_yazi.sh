#!/usr/bin/env bash
set -e

# command name to installed
name="yazi"

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

  url=https://github.com/sxyazi/yazi/releases/download/nightly/yazi-x86_64-unknown-linux-gnu.zip
  wget -O yazi.zip $url
  unzip yazi.zip && mv yazi-* yazi_pkg

  mv yazi_pkg/ya* .

  rm yazi.zip && rm -rf yazi_pkg
}

# check dependencies installed
src_dir=$(dirname $0)
$src_dir/dependencies/install_fd.sh --quiet
$src_dir/dependencies/install_glow.sh --quiet
$src_dir/dependencies/install_unzip.sh --quiet

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
