#myset.sh
source $USER_CUSTOM/rc/myset.sh

###################################################
# If not running interactively, don't do anything
[[ $- != *i* ]] && return

###################################################
# PS1
export PS1=$FALLBACK_PS1
