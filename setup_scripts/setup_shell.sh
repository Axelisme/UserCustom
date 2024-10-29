#!/usr/bin/env bash
set -e

UserCustom=$(dirname $(dirname $(realpath "$0")))

cp -b $UserCustom/home/.bashrc ~/.bashrc # setup bashrc
cp -b $UserCustom/home/.zshrc ~/.zshrc   # setup zshrc
ln -b $UserCustom/home/.vimrc ~/.vimrc   # setup vimrc

# setup config files
for src in $(realpath $UserCustom/home/.config/*); do
  dst=$HOME/.config/$(basename $src)

  # if dst exists and not a link, backup it
  if [ -e $dst ]; then
    if [ ! -L $dst ]; then
      echo "backup $dst"
      mv -b $dst $dst.bak
    else
      echo "skip $dst"
      continue
    fi
  fi

  # link src to dst
  if [ -d $src ]; then # is directory
    # soft link
    ln -Ts $src $dst
  else # is file
    # hard link
    ln $src $dst
  fi
done
