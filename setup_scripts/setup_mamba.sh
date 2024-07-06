#!/usr/bin/env bash

eval "$(micromamba shell hook -s posix)"
[[ -f $HOME/.bashrc ]] && micromamba shell init -s bash;
[[ -f $HOME/.zshrc ]] && micromamba shell init -s zsh;
micromamba config append channels conda-forge
micromamba config set channel_priority strict