#!/bin/bash

wget -P ~/Downloads/ https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh;
bash ~/Downloads/Miniconda3-latest-Linux-x86_64.sh;
source $HOME/.bashrc;
[[ -f $HOME/.zshrc ]] && conda init zsh;
conda config --set auto_activate_base false