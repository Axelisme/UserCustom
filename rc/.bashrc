#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
[[ -f $USER_CUSTOM/rc/mybash.sh ]] && source $USER_CUSTOM/rc/mybash.sh

