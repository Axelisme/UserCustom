###################################################
# myset.sh
source $USER_CUSTOM/rc/myset.sh

###################################################
# If not running interactively, don't do anything
[[ $- != *i* ]] && return

###################################################
ZDOTDIR=$HOME/.config
if [[ ! -f ${ZDOTDIR:-${HOME}}/.zcomet/bin/zcomet.zsh ]]; then
  command git clone https://github.com/agkozak/zcomet.git ${ZDOTDIR:-${HOME}}/.zcomet/bin
fi

source ${ZDOTDIR:-${HOME}}/.zcomet/bin/zcomet.zsh

zcomet trigger extract x ohmyzsh plugins/extract
zcomet load zdharma-continuum/fast-syntax-highlighting
zcomet load ohmyzsh plugins/sudo
zcomet load ohmyzsh plugins/gitfast
zcomet load ohmyzsh lib/completion.zsh
zcomet load ohmyzsh lib/clipboard.zsh
zcomet load zsh-users/zsh-history-substring-search
zcomet load zsh-users/zsh-completions
zcomet load zsh-users/zsh-autosuggestions

zcomet compinit

# Keybindings
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
bindkey '\033[H' beginning-of-line
bindkey '\033[F' end-of-line
bindkey '^[[3~' delete-char
bindkey '^[[1;5C' forward-word
bindkey '^[[1;5D' backward-word

# History
HISTSIZE=5000
HISTFILE=~/.cache/zsh_history
SAVEHIST=$HISTSIZE
HISTDUP=erase
setopt appendhistory
setopt sharehistory
setopt hist_ignore_space
setopt hist_ignore_all_dups
setopt hist_save_no_dups
setopt hist_ignore_dups
setopt hist_find_no_dups

# Prompt
if command -v oh-my-posh &>/dev/null; then
  if command -v tput &>/dev/null && [[ $(tput colors) == "256" ]]; then
    ohmyposh_cfg=$HOME/.config/ohmyposh/main.yaml
  else
    ohmyposh_cfg=$HOME/.config/ohmyposh/tty.yaml
  fi
  eval "$(oh-my-posh init zsh --config $ohmyposh_cfg)"
else
  setopt PROMPT_SUBST
  export PROMPT=$FALLBACK_PROMPT
fi
