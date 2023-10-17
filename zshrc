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

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
export CRYPTOGRAPHY_OPENSSL_NO_LEGACY=1
__conda_setup="$('/opt/miniconda3/bin/conda' 'shell.zsh' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/opt/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/opt/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<
