#!/usr/bin/env bash

mkdir -p ~/.local/bin
cd ~/.local/bin
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj micromamba
cd -
