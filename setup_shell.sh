#!/bin/bash

# recursive copy, if file exists, backup it
backup_apply() {                               # backup_apply command src dst flag
    local cmd=$1 src=$2 dst=$3 flag=$4

    if [[ ! -e $src ]]; then                    # if src not exists
        echo "Error: $src not exists"
    elif [[ -d $src ]]; then                    # if src is a directory
        if [[ -e $dst ]]; then                  # if dst exists
            if [[ $src -ef $dst ]]; then        # if src and dst are the same
                echo "Skip $dst"
                return
            elif [[ ! -d $dst ]]; then          # if dst is not a directory
                echo "Backup $dst"
                mv $dst $dst.bak
            fi
        fi
        mkdir -p $dst                           # create dst directory
        for file in $(\ls $src); do
            backup_apply $1 $src/$file $dst/$file
        done
    elif [[ -f $src ]]; then                    # if src is a file
        if [[ -e $dst ]]; then                  # if dst exists
            if [[ $src -ef $dst ]]; then        # if src and dst are the same
                echo "Skip $dst"
                return
            fi
            echo "Backup $dst"
            mv --backup=numbered $dst $dst.bak  # backup dst
        fi
        $cmd $flag $src $dst
    fi
}

UserCustom=$(dirname "$0")
backup_apply cp $UserCustom/rc/.bashrc ~/.bashrc # setup bashrc
backup_apply cp $UserCustom/rc/.zshrc  ~/.zshrc   # setup zshrc
backup_apply ln $UserCustom/rc/.vimrc  ~/.vimrc   # setup vimrc
backup_apply ln $UserCustom/.config    ~/.config    # setup config

unset backup_ln