#!/usr/bin/env bash

# if fcitx5 is not installed, show a warning and exit
if ! command -v fcitx5 &>/dev/null; then
  echo "fcitx5 could not be found. Please install fcitx5 and try again."
  exit
fi

# if rime is not installed, show a warning and exit
if ! command -v rime_patch &>/dev/null; then
  echo "rime could not be found. Please install rime and try again."
  exit
fi

UserCustom=$(dirname $(dirname $(realpath "$0")))

src_dir=$UserCustom/home/.local/share/fcitx5/rime
dst_dir=$HOME/.local/share/fcitx5/rime

install_rime_frost() {
  echo "install rime_frost"
  git clone --depth 1 https://github.com/gaboolic/rime-frost $dst_dir
}

# check if rime dir exists
if [[ -e $dst_dir ]]; then
  # check if rime_frost is installed
  if [[ ! -e $dst_dir/rime_frost.schema.yaml ]]; then
    # backup rime dir
    echo "backup $dst_dir"
    mv -b $dst_dir $dst_dir.bak
    install_rime_frost
  else
    echo "rime_frost is already installed"
  fi
else
  install_rime_frost
fi

unset install_rime_frost

echo "overwrite custom rime config"
cp -TRb $src_dir $dst_dir
