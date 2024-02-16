####################################################
# env
source $USER_CUSTOM/rc/env.sh

####################################################
# alias
source $USER_CUSTOM/rc/aliases.sh

####################################################
# nnn
export GUI=1
export NNN_OPTS="aAceEruU"
export NNN_COLORS='1234'
export NNN_OPENER=$HOME/.config/nnn/plugins/nuke
export NNN_COPIER=$HOME/.config/nnn/plugins/.cbcp
export NNN_PLUG='e:suedit;d:diffs;D:dups;P:preview-tabbed'
export NNN_SSHFS='sshfs -C -o delay_connect,idmap=user,follow_symlinks,auto_cache,cache_timeout=3600'
export NNN_BMS="M:$HOME/.config/nnn/mounts/;P:$HOME/.config/nnn/plugins;D:$HOME/Downloads/;H:$HOME/"

n ()
{
    if [[ "${NNNLVL:-0}" -ge 1 ]]; then
        echo "nnn is already running"
        return
    fi
    NNN_TMPFILE="${XDG_CONFIG_HOME:-$HOME/.config}/nnn/.lastd"
    \nnn "$@"
    if [ -f "$NNN_TMPFILE" ]; then
            . "$NNN_TMPFILE"
            rm -f "$NNN_TMPFILE" > /dev/null
    fi
}
