#!/usr/bin/env bash
set -e

# if micromamba is not installed, show a warning and exit
if ! type micromamba >/dev/null 2>&1; then
  echo "micromamba could not be found. Please install micromamba and try again."
  exit
fi

[[ -f $HOME/.bashrc ]] && micromamba shell init -s bash
[[ -f $HOME/.zshrc ]] && micromamba shell init -s zsh
micromamba config append channels conda-forge
micromamba config set channel_priority strict
