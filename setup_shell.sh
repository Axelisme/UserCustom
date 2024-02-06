#!/bin/bash

# recursive copy, if file exists, backup it
backup_apply() {
    local src=$2 dst=$3

    if [[ ! -e $src ]]; then
        echo "Error: $src not exists"
    elif [[ -d $src ]]; then
        if [[ -e $dst ]] && [[ ! -d $dst ]]; then
            echo "Backup $dst"
            mv $dst $dst.bak
        fi
        mkdir -p $dst
        for file in $(\ls $src); do
            backup_apply $1 $src/$file $dst/$file
        done
    elif [[ -f $src ]]; then
        if [[ -e $dst ]]; then
            echo "Backup $dst"
            mv $dst $dst.bak
        fi
        # $1 is the copy or move command
        $1 $src $dst
    fi
}

UserCustom=$(dirname "$0")
backup_apply cp $UserCustom/rc/.bashrc ~/.bashrc # setup bashrc
backup_apply cp $UserCustom/rc/.zshrc ~/.zshrc   # setup zshrc
backup_apply ln $UserCustom/rc/.vimrc ~/.vimrc   # setup vimrc
backup_apply ln $UserCustom/.config ~/.config    # setup config

unset backup_ln