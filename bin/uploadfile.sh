#!/usr/bin/bash

CloudName='AxelCloud'
SRC_PATH="${HOME}/"
DES_PATH='其他/Home_backup/'
INCLUDE_PATH="$USER_CUSTOM/backup.txt"
FLAGS=" -P --skip-links --transfers 8 --auto-confirm "

echo "*****From:${SRC_PATH}  To:${DES_PATH} *****";
rclone sync $FLAGS ${SRC_PATH} $CloudName:${DES_PATH} --include-from=$INCLUDE_PATH
