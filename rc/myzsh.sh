###################################################
# myset.sh
source $USER_CUSTOM/rc/myset.sh

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

# 加载主题
zinit ice depth=1; zinit light romkatv/powerlevel10k

# 插件
zinit light Aloxaf/fzf-tab
zinit light zsh-users/zsh-completions
zinit light zsh-users/zsh-autosuggestions
zinit light zdharma-continuum/fast-syntax-highlighting
zinit snippet OMZP::git
zinit snippet OMZP::sudo
zinit snippet OMZP::extract
zinit snippet OMZP::command-not-found

# Load completions
autoload -Uz compinit && compinit
zinit cdreplay -q

# Keybindings
bindkey -e
bindkey '^[[A' history-search-backward
bindkey '^[[B' history-search-forward
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
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' menu no
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'ls --color $realpath'
zstyle ':fzf-tab:complete:__zoxide_z:*' fzf-preview 'ls --color $realpath'

# Shell integrations
type fzf > /dev/null && eval "$(fzf --zsh)"
type zoxide > /dev/null && eval "$(zoxide init zsh)" && alias cd='z'