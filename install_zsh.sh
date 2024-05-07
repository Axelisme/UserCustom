#!/bin/bash

cd ~/.local/bin
wget -O zsh_installer https://raw.githubusercontent.com/romkatv/zsh-bin/master/install
bash ./zsh_installer
wget -O zinit.sh https://raw.githubusercontent.com/zdharma-continuum/zinit/HEAD/scripts/install.sh
bash ./zinit.sh
cd -
