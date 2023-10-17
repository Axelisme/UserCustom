#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

alias ls='ls --color=auto'
alias grep='grep --color=auto'
PS1='[\u@\h \W]\$ '

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
[ -f $USER_CUSTOM/mybash.sh ] && source $USER_CUSTOM/mybash.sh

exec zsh