#!/bin/bash

wget -P ~/Downloads/ https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh;
bash ~/Downloads/Miniconda3-latest-Linux-x86_64.sh;
[[ -f $HOME/.zshrc ]] && bash -i -c 'conda init zsh';
bash -i -c 'conda config --set auto_activate_base false';