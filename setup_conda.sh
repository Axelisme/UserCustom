#!/usr/bin/env bash

[[ -f $HOME/.bashrc ]] && conda init bash;
[[ -f $HOME/.zshrc ]] && conda init zsh;
bash -i -c 'conda config --set auto_activate_base false';
