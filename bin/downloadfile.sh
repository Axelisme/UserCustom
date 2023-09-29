#!/usr/bin/bash

CloudName='AxelCloud'
SRC_PATH='其他/Home_backup/'
DES_PATH="${HOME}/"
FLAGS=" -P --skip-links --transfers 8 --auto-confirm "
echo "*****From:${SRC_PATH}  To:${DES_PATH} *****";
rclone copy $FLAGS $CloudName:${SRC_PATH} ${DES_PATH};

