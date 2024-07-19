#!/usr/bin/env bash

# if conda is not installed, show a warning and exit
if ! type conda > /dev/null 2>&1; then
  echo "conda could not be found. Please install conda and try again."
  exit
fi

[[ -f $HOME/.bashrc ]] && conda init bash;
[[ -f $HOME/.zshrc ]] && conda init zsh;
bash -i -c 'conda config --set auto_activate_base false';
