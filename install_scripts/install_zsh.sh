#!/usr/bin/env bash

mkdir -p ~/.local/bin
cd ~/.local/bin
wget -O zsh_installer https://raw.githubusercontent.com/romkatv/zsh-bin/master/install
bash ./zsh_installer
cd -