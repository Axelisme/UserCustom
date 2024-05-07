#!/bin/bash

cd ~/.local
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
eval "$(./bin/micromamba shell hook -s posix)"
[[ -f $HOME/.zshrc ]] && micromamba shell init -s zsh
micromamba config append channels conda-forge
micromamba config set channel_priority strict
cd -
