#!/usr/bin/env bash
set -e

src_dir=$(dirname $0)

$src_dir/install_unzip.sh
$src_dir/install_fd.sh
$src_dir/install_fzf.sh
$src_dir/install_lazygit.sh
$src_dir/install_lsd.sh
$src_dir/install_mamba.sh
$src_dir/install_neovim.sh
$src_dir/install_magick.sh
$src_dir/install_nnn.sh
$src_dir/install_yazi.sh
$src_dir/install_ohmyposh.sh
$src_dir/install_ripgrep.sh
$src_dir/install_zsh.sh
