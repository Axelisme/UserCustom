#!/usr/bin/env bash
set -e

UserCustom=$(dirname $(dirname $(realpath "$0")))

cp -b $UserCustom/home/.bashrc ~/.bashrc # setup bashrc
cp -b $UserCustom/home/.zshrc ~/.zshrc   # setup zshrc
ln -b $UserCustom/home/.vimrc ~/.vimrc   # setup vimrc
