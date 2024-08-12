#!/usr/bin/env bash

if ! command -v mamba &> /dev/null; then
    echo "installing mamba"
    mkdir -p ~/.local/bin
    cd ~/.local
    curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
    cd -
else
    echo "mamba already installed"
fi