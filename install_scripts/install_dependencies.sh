#!/usr/bin/env bash

mkdir -p ~/.local/bin
cd ~/.local/bin

# neovim
if ! command -v nvim &> /dev/null; then
    echo "installing neovim"
    wget -O nvim.tar.gz https://github.com/neovim/neovim/releases/download/nightly/nvim-linux64.tar.gz
    tar zxvf nvim.tar.gz -C ~/.local --strip-components=1
    rm nvim.tar.gz
fi

# lsd
if ! command -v lsd &> /dev/null; then
    echo "installing lsd"
    wget -O lsd.tar.gz https://github.com/lsd-rs/lsd/releases/download/v1.1.2/lsd-v1.1.2-x86_64-unknown-linux-gnu.tar.gz
    tar zxvf lsd.tar.gz
    mv lsd-v1.1.2-*/lsd lsd
    rm -r lsd.tar.gz lsd-v1.1.2-*
fi

# ripgrep
if ! command -v rg &> /dev/null; then
    echo "installing ripgrep"
    wget -O ripgrep.tar.gz https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/ripgrep-14.1.0-x86_64-unknown-linux-musl.tar.gz
    tar zxvf ripgrep.tar.gz
    mv ripgrep-14.1.0-*/rg rg
    rm -r ripgrep.tar.gz ripgrep-14.1.0-*
fi

# lazygit
if ! command -v lazygit &> /dev/null; then
    echo "installing lazygit"
    wget -O lazygit.tar.gz https://github.com/jesseduffield/lazygit/releases/download/v0.43.1/lazygit_0.43.1_Linux_x86_64.tar.gz
    tar zxvf lazygit.tar.gz lazygit
    rm lazygit.tar.gz
fi

# fzf
if ! command -v fzf &> /dev/null; then
    echo "installing fzf"
    wget -O fzf.tar.gz https://github.com/junegunn/fzf/releases/download/v0.54.3/fzf-0.54.3-linux_amd64.tar.gz
    tar zxvf fzf.tar.gz fzf
    rm fzf.tar.gz
fi

# fd
if ! command -v fd &> /dev/null; then
    echo "installing fd"
    wget -O fd.tar.gz https://github.com/sharkdp/fd/releases/download/v10.1.0/fd-v10.1.0-x86_64-unknown-linux-gnu.tar.gz
    tar zxvf fd.tar.gz
    mv fd-v10.1.0-*/fd fd
    rm -r fd.tar.gz fd-v10.1.0-*
fi