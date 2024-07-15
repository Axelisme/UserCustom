# general setting
export LANG=en_US.UTF-8
export PATH=$HOME/.local/bin:$PATH

# editor & visual
if type nvim > /dev/null; then
  export VISUAL=nvim
  export EDITOR=nvim
else
  export VISUAL=vim
  export EDITOR=vim
fi

# asign python cache dir to /tmp
export PYTHONPYCACHEPREFIX=/tmp
# use multithread to unzip xz file
export XZ_DEFAULTS='-T0'
# no .gnupg in home directory
export GNUPGHOME="${XDG_DATA_HOME:-$HOME/.local/share}/gnupg"
