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
# cp & mv
alias cp='cp -av'
alias mv='mv -v'
# grep
alias grep='grep --color=auto'
# mamba
type micromamba > /dev/null && alias mamba='micromamba'
