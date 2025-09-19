#!/usr/bin/env bash

UserCustom=$(dirname $(dirname $(realpath "$0")))

src_dir=$UserCustom/home/.local/bin
dst_dir=$HOME/.local/bin
bin=kh-volume-daemon

mkdir -p $dst_dir

echo "overwrite kh-volume-daemon"
ln $src_dir/$bin $dst_dir/$bin
