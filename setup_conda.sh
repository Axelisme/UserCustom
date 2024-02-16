#!/bin/bash

conda init bash;
[[ -f $HOME/.zshrc ]] && conda init zsh;
bash -i -c 'conda config --set auto_activate_base false';