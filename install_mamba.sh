#!/bin/bash

cd ~/Downloads
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
eval "$(./bin/micromamba shell hook -s posix)"
[[ -f $HOME/.zshrc ]] && ./bin/micromamba shell init -s zsh
cd -