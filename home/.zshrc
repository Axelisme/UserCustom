# added by Nix installer
if [ -e /home/axel/.nix-profile/etc/profile.d/nix.sh ]; then . /home/axel/.nix-profile/etc/profile.d/nix.sh; fi

#Set up my custom command
export USER_CUSTOM=$HOME/UserCustom
[[ -f $USER_CUSTOM/rc/myzsh.sh ]] && source $USER_CUSTOM/rc/myzsh.sh

# mamba initialize
export MAMBA_ROOT_PREFIX="$HOME/micromamba"
eval "$(micromamba shell hook --shell bash)" 
