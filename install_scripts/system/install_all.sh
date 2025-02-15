#!/usr/bin/env bash
set -e

src_dir=$(dirname $0)

# zsh shell
$src_dir/install_zsh.sh

# editor
$src_dir/install_neovim.sh

# file manager
$src_dir/install_nnn.sh
$src_dir/install_yazi.sh

# other commands
$src_dir/install_nix.sh
$src_dir/install_lazygit.sh
$src_dir/install_mamba.sh
