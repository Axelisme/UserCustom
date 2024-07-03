# If not running interactively, don't do anything
[[ $- != *i* ]] && return

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
[[ -f $USER_CUSTOM/rc/myzsh.sh ]] && source $USER_CUSTOM/rc/myzsh.sh
