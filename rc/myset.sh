# env
source $USER_CUSTOM/rc/env.sh

####################################################
# alias
source $USER_CUSTOM/rc/aliases.sh

####################################################
# fallback ps1
parse_ip() {
  ip route get 1.1.1.1 | awk -F"src " 'NR == 1{ split($2, a," ");print a[1]}'
}
parse_git_branch() {
  git branch 2>/dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/ (\1)/'
}
braket=$(tput setaf 82)
workdir=$(tput setaf 33)
gitbranch=$(tput setaf 226)
reset=$(tput sgr0)
FALLBACK_PS1="\[$braket\][\$(parse_ip)\[$braket\]]:\[$workdir\]\w\[$gitbranch\]\$(parse_git_branch)\n\u\[$reset\]$ "
NEWLINE=$'\n'
FALLBACK_PROMPT="%F{82}[\$(parse_ip)]:%F{33}%~%F{226}\$(parse_git_branch)$NEWLINE%n%f\$ "

####################################################
# nnn
if type nnn >/dev/null 2>&1; then
  export GUI=0
  export NNN_OPTS="aceEuUx"
  export NNN_COLORS='1234'
  export NNN_OPENER=$HOME/.config/nnn/plugins/nuke
  export NNN_COPIER=$HOME/.config/nnn/plugins/.cbcp
  export NNN_PLUG='e:suedit;'
  export NNN_SSHFS='sshfs -C -o delay_connect,idmap=user,follow_symlinks,auto_cache,cache_timeout=3600'
  export NNN_BMS="M:$HOME/.config/nnn/mounts/;P:$HOME/.config/nnn/plugins;D:$HOME/Downloads/;H:$HOME/"

  alias nnn="nnn_cd"
  alias N="sudo nnn_cd"

  nnn_cd() {
    if [[ "${NNNLVL:-0}" -ge 1 ]]; then
      echo "nnn is already running"
      return
    fi
    NNN_TMPFILE="${XDG_CONFIG_HOME:-$HOME/.config}/nnn/.lastd"
    \nnn "$@"
    if [ -f "$NNN_TMPFILE" ]; then
      . "$NNN_TMPFILE"
      rm -f "$NNN_TMPFILE" >/dev/null
    fi
  }
fi

####################################################
# fzf
if type fzf >/dev/null 2>&1; then
  if type fd >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND='fd --type f --hidden --color=always --follow --exclude  .git --ignore-file ~/.gitignore'
  fi

  export FZF_DEFAULT_OPTS='--multi --ansi'
fi

####################################################
# yazi
if type yazi >/dev/null 2>&1; then
  function y() {
    local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
    yazi "$@" --cwd-file="$tmp"
    if cwd="$(command cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
      builtin cd -- "$cwd"
    fi
    rm -f -- "$tmp"
  }
fi
