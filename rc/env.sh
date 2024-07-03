export LANG=en_US.UTF-8
if type nvim > /dev/null; then
  export VISUAL=nvim
  export EDITOR=nvim
else
  export VISUAL=vim
  export EDITOR=vim
fi
export PATH=$HOME/.local/bin:$PATH
export PYTHONPYCACHEPREFIX=/tmp
export XZ_DEFAULTS='-T0'
