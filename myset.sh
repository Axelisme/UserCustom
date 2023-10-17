####################################################
# env
source $USER_CUSTOM/env.sh

####################################################
# alias
source $USER_CUSTOM/aliases.sh

####################################################
# nnn
export GUI=0
export NNN_OPTS="cEUxi"
export NNN_COLORS='1234'
export NNN_FIFO=/tmp/nnn_${USER}_$$.fifo
export NNN_OPENER=~/.config/nnn/plugins/nuke
export NNN_COPIER=~/.config/nnn/plugins/.cbcp
export NNN_PLUG='e:suedit;'

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
