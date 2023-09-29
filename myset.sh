####################################################
# env
source $USER_CUSTOM/env.sh

####################################################
# alias
source $USER_CUSTOM/aliases.sh

####################################################
# nnn
export GUI=1
export NNN_OPTS="cEUxi"
export NNN_COLORS='1234'
export NNN_FIFO=/tmp/nnn_${USER}_$$.fifo
export NNN_OPENER=~/.config/nnn/plugins/nuke
export NNN_COPIER=~/.config/nnn/plugins/.cbcp
export NNN_PLUG='e:suedit;o:!&open $nnn*;f:fzcd;'
export NNN_ARCHIVE="\\.(7z|a|ace|alz|arc|arj|bz|bz2|cab|cpio|deb|gz|jar|lha|lz|lzh|lzma|lzo|rar|rpm|rz|t7z|tar|tbz|tbz2|tgz|tlz|txz|tZ|tzo|war|xpi|xz|Z|zip)$"

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

####################################################
#fzf
export FZF_DEFAULT_COMMAND='
        fd --hidden --glob --follow --max-depth 10 --strip-cwd-prefix --exclude .git --exclude build '
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_CTRL_T_OPTS="
        --height 50% --reverse --border --keep-right "
export FZF_CTRL_R_OPTS="$FZF_CTRL_T_OPTS"
