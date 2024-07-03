# nnn
type nnn > /dev/null && alias N='sudo -E nnn'

# ls
if type tput > /dev/null && [[ `tput colors` == "256" ]] && type lsd > /dev/null; then
    alias ls='lsd'
    alias ll='lsd -l'
    alias la='lsd -lA'
else
    alias ls='ls --color=auto'
    alias ll='ls -l'
    alias la='ls -lA'
fi

# neovim
type nvim > /dev/null && alias vim='nvim'

# cp & mv
if type cpg > /dev/null; then
    alias cp='advcp -ag'
    alias mv='advmv -g'
else
    alias cp='cp -av'
    alias mv='mv -v'
fi

# grep
alias grep='grep --color=auto'

# mamba
type micromamba > /dev/null && alias mamba='micromamba'