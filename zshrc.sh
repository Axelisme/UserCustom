# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
export zinit=$HOME/.local/share/zinit/zinit.git/zinit.zsh
[ -f $USER_CUSTOM/myzsh.sh ] && source $USER_CUSTOM/myzsh.sh

# To customize prompt, run `p10k configure` or edit ~/UserCustom/p10k/gui.zsh.
[[ ! -f ~/UserCustom/p10k/ssh.zsh ]] || source ~/UserCustom/p10k/ssh.zsh