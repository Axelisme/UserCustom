#!/bin/bash

# recursive copy, if file exists, backup it
backup_ln() {
    local src=$1 dst=$2

    if [[ ! -e $src ]]; then
        echo "Error: $src not exists"
    elif [[ -d $src ]]; then
        if [[ -e $dst ]] && [[ ! -d $dst ]]; then
            echo "Backup $dst"
            mv $dst $dst.bak
        fi
        mkdir -p $dst
        for file in $(ls $src); do
            backup_ln $src/$file $dst/$file
        done
    elif [[ -f $src ]]; then
        if [[ -e $dst ]]; then
            echo "Backup $dst"
            mv $dst $dst.bak
        fi
        ln $src $dst
    fi
}

UserCustom=$(dirname "$0")
backup_ln $UserCustom/rc/.bashrc ~/.bashrc # setup bashrc
backup_ln $UserCustom/rc/.zshrc ~/.zshrc   # setup zshrc
backup_ln $UserCustom/rc/.vimrc ~/.vimrc   # setup vimrc
backup_ln $UserCustom/.config ~/.config    # setup config

unset backup_ln