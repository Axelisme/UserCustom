#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

parse_git_branch() {
     git branch 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/ (\1)/'
}
braket=$(tput setaf 82)
workdir=$(tput setaf 33)
gitbranch=$(tput setaf 226)
reset=$(tput sgr0)
PS1="\[$braket\][ \[$workdir\]\w \[$braket\]] \[$gitbranch\]\$(parse_git_branch)\n\[$reset\]$ ";

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
[[ -f $USER_CUSTOM/rc/mybash.sh ]] && source $USER_CUSTOM/rc/mybash.sh

