#!/usr/bin/env bash
set -e

UserCustom=$(dirname $(dirname $(realpath "$0")))

# setup config files
backup_cp() {
  src_dir=$1
  dst_dir=$2
  mkdir -p $dst_dir
  for src in $(realpath $src_dir/*); do
    dst=$dst_dir/$(basename $src)

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
}

backup_cp $UserCustom/home/.config $HOME/.config
backup_cp $UserCustom/home/.local/include $HOME/.local/include
