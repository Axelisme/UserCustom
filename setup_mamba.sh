#!/usr/bin/env bash

[[ -f $HOME/.bashrc ]] && micromamba shell init -s bash;
[[ -f $HOME/.zshrc ]] && micromamba shell init -s zsh;
