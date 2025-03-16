# general setting
export LANG=en_US.UTF-8
export PATH=$HOME/.local/bin:$PATH
export C_INCLUDE_PATH=$HOME/.local/include:$C_INCLUDE_PATH
export CPLUS_INCLUDE_PATH=$HOME/.local/include:$CPLUS_INCLUDE_PATH
export LD_LIBRARY_PATH=$HOME/.local/lib:$LD_LIBRARY_PATH

# editor & visual
if command -v nvim &>/dev/null && nvim -v &>/dev/null; then
  export VISUAL=nvim
  export EDITOR=nvim
elif command -v vim &>/dev/null; then
  export VISUAL=vim
  export EDITOR=vim
fi

# asign python cache dir to /tmp
export PYTHONPYCACHEPREFIX=/tmp
# use multithread to unzip xz file
export XZ_DEFAULTS='-T0'
# no .gnupg in home directory
export GNUPGHOME="${XDG_DATA_HOME:-$HOME/.local/share}/gnupg"

# micromamba
if command -v micromamba &>/dev/null; then
  export MAMBA_ROOT_PREFIX=$HOME/.local/share/micromamba
fi
