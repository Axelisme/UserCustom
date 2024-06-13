# nnn
type nnn > /dev/null 2>&1 && alias N='sudo -E nnn'
# ls
if type tput > /dev/null 2>&1 && [[ `tput colors` == "256" ]] && type lsd > /dev/null 2>&1; then
    alias ls='lsd'
    alias ll='lsd -l'
    alias la='lsd -lA'
else
    alias ls='ls --color=auto'
    alias ll='ls -l'
    alias la='ls -lA'
fi
# cp & mv
alias cp='cp -av'
alias mv='mv -v'
# grep
alias grep='grep --color=auto'
# mamba
type micromamba > /dev/null 2>&1 && alias mamba='micromamba'
