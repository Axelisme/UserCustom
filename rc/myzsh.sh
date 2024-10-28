###################################################
# myset.sh
source $USER_CUSTOM/rc/myset.sh

###################################################
# If not running interactively, don't do anything
[[ $- != *i* ]] && return

###################################################
# ZINIT_HOME
ZINIT_HOME=/usr/share/zinit
# Download Zinit, if it's not there yet
if [ ! -d "$ZINIT_HOME" ]; then
  ZINIT_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}/zinit/zinit.git"
  if [ ! -d "$ZINIT_HOME" ]; then
    git clone --depth 1 https://github.com/zdharma-continuum/zinit.git "$ZINIT_HOME"
  fi
fi

# 加载zinit
source $ZINIT_HOME/zinit.zsh

# 插件
function _history_substring_search_config() {
  bindkey '^[[A' history-substring-search-up
  bindkey '^[[B' history-substring-search-down
}

zinit wait lucid wait for \
  atinit"zicompinit; zicdreplay" zdharma/fast-syntax-highlighting \
  atload'_zsh_autosuggest_start' zsh-users/zsh-autosuggestions \
  atpull'zinit creinstall -q .' zsh-users/zsh-completions \
  atload'_history_substring_search_config' zsh-users/zsh-history-substring-search \
  OMZP::sudo \
  OMZP::extract \
  OMZL::completion.zsh \
  OMZL::clipboard.zsh
# command -v fzf &>/dev/null && zinit light Aloxaf/fzf-tab
unset _history_substring_search_config

# Keybindings
bindkey '\033[H' beginning-of-line
bindkey '\033[F' end-of-line
bindkey '^[[3~' delete-char
bindkey '^[[1;5C' forward-word
bindkey '^[[1;5D' backward-word

# History
HISTSIZE=5000
HISTFILE=~/.zsh_history
SAVEHIST=$HISTSIZE
HISTDUP=erase
setopt appendhistory
setopt sharehistory
setopt hist_ignore_space
setopt hist_ignore_all_dups
setopt hist_save_no_dups
setopt hist_ignore_dups
setopt hist_find_no_dups

# Completion styling
# zstyle ':completion:*' menu no
# if command -v fzf &>/dev/null; then
#   zstyle ':fzf-tab:*' continuous-trigger '/'
#   zstyle ':fzf-tab:complete:*' fzf-bindings 'shift-tab:toggle+down,ctrl-a:toggle-all'
# fi

# Prompt
if command -v oh-my-posh &>/dev/null; then
  if command -v tput &>/dev/null && [[ $(tput colors) == "256" ]]; then
    if [[ -v SSH_TTY ]]; then
      ohmyposh_cfg=$HOME/.config/ohmyposh/ssh.toml
    else
      ohmyposh_cfg=$HOME/.config/ohmyposh/main.toml
    fi
  else
    ohmyposh_cfg=$HOME/.config/ohmyposh/tty.toml
  fi
  eval "$(oh-my-posh init zsh --config $ohmyposh_cfg)"
else
  setopt PROMPT_SUBST
  export PROMPT=$FALLBACK_PROMPT
fi
