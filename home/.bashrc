#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
[[ -f $USER_CUSTOM/rc/mybash.sh ]] && source $USER_CUSTOM/rc/mybash.sh

# mamba initialize
if command -v micromamba >/dev/null 2>&1; then
  eval "$(micromamba shell hook --shell bash)"
fi
