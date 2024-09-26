# ls
if type tput >/dev/null 2>&1 && [[ $(tput colors) == "256" ]] && type lsd >/dev/null 2>&1; then
  alias ls='lsd'
  alias ll='lsd -l'
  alias la='lsd -lA'
else
  alias ls='ls --color=auto'
  alias ll='ls -l'
  alias la='ls -lA'
fi

# neovim
type nvim >/dev/null 2>&1 && alias vim='nvim'

# lazygit
type lazygit >/dev/null 2>&1 && alias lg='lazygit'

# cp & mv
if type cpg >/dev/null 2>&1; then
  alias cp='advcp -ag'
  alias mv='advmv -g'
else
  alias cp='cp -av'
  alias mv='mv -v'
fi

# grep
alias grep='grep --color=auto'

# mamba
type micromamba >/dev/null 2>&1 && alias mmba='micromamba'

# kitty
[[ -n $KITTY_WINDOW_ID ]] && alias ssh='kitty +kitten ssh'
