# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
export ZINIT_PATH=/usr/share/zinit/zinit.zsh
[[ -f $USER_CUSTOM/rc/myzsh.sh ]] && source $USER_CUSTOM/rc/myzsh.sh

# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
if [[ `tput colors` == "256" ]]; then
    [[ ! -f $USER_CUSTOM/p10k/gui.zsh ]] || source $USER_CUSTOM/p10k/gui.zsh
else
    [[ ! -f $USER_CUSTOM/p10k/tty.zsh ]] || source $USER_CUSTOM/p10k/tty.zsh
fi

type zoxide > /dev/null && eval "$(zoxide init zsh)"