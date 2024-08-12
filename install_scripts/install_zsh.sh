#!/usr/bin/env bash

if ! command -v zsh &> /dev/null; then
    echo "installing zsh"
    mkdir -p ~/.local/bin
    cd ~/.local/bin
    wget -O zsh_installer https://raw.githubusercontent.com/romkatv/zsh-bin/master/install
    bash ./zsh_installer
    cd -
else
    echo "zsh already installed"
fi