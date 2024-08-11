#!/usr/bin/env bash

# mkdir -p ~/.local/bin
# cd ~/.local/bin
# wget -O nnn.tar.gz https://github.com/jarun/nnn/releases/download/v4.9/nnn-static-4.9.x86_64.tar.gz
# tar zxvf nnn.tar.gz
# mv nnn-static nnn
# cd -

if ! command -v nnn &> /dev/null; then
    echo "installing nnn"
    mkdir -p ~/.local/bin
    cd ~/.local/bin
    wget -O nnn.tar.gz https://github.com/jarun/nnn/releases/download/v4.9/nnn-static-4.9.x86_64.tar.gz
    tar zxvf nnn.tar.gz
    mv nnn-static nnn
    rm nnn.tar.gz
    cd -
else
    echo "nnn already installed"
fi
