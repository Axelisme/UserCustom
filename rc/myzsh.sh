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
    mkdir -p "$(dirname $ZINIT_HOME)"
    git clone https://github.com/zdharma-continuum/zinit.git "$ZINIT_HOME"
  fi
fi

# 加载zinit
source $ZINIT_HOME/zinit.zsh

# Load completions
autoload -Uz compinit && compinit

# 插件
type fzf >/dev/null && zinit light Aloxaf/fzf-tab
zinit light zsh-users/zsh-completions
zinit light zsh-users/zsh-autosuggestions
zinit light zdharma-continuum/fast-syntax-highlighting
type git >/dev/null && zinit snippet OMZP::git
zinit snippet OMZP::sudo
zinit snippet OMZP::extract
zinit snippet OMZL::completion.zsh
# zinit snippet OMZL::key-bindings.zsh
zinit snippet OMZP::command-not-found

# Keybindings
zinit load 'zsh-users/zsh-history-substring-search'
# zinit ice wait atload '_history_substring_search_config'
bindkey -e
bindkey '^[[A' history-substring-search-up
bindkey '^[[B' history-substring-search-down
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
# zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
# zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' menu no
if type fzf >/dev/null; then
  zstyle ':fzf-tab:*' continuous-trigger '/'
  zstyle ':fzf-tab:complete:*' fzf-bindings 'shift-tab:toggle+down,ctrl-a:toggle-all'
fi

# Shell integrations
# type zoxide > /dev/null && eval "$(zoxide init zsh)" && alias cd='z'

# Prompt
if type oh-my-posh >/dev/null; then
  if type tput >/dev/null && [[ $(tput colors) == "256" ]]; then
    if [[ -v SSH_TTY ]]; then
      eval "$(oh-my-posh init zsh --config $HOME/.config/ohmyposh/ssh.toml)"
    else
      eval "$(oh-my-posh init zsh --config $HOME/.config/ohmyposh/main.toml)"
    fi
  else
    eval "$(oh-my-posh init zsh --config $HOME/.config/ohmyposh/tty.toml)"
  fi
else
  setopt PROMPT_SUBST
  export PROMPT=$FALLBACK_PROMPT
fi
