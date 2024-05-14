###################################################
#myset.sh
source $USER_CUSTOM/rc/myset.sh

# PS1
parse_ip() {
    ip route get 1.1.1.1 | awk -F"src " 'NR == 1{ split($2, a," ");print a[1]}'
}
parse_git_branch() {
    git branch 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/ (\1)/'
}
braket=$(tput setaf 82)
workdir=$(tput setaf 33)
gitbranch=$(tput setaf 226)
reset=$(tput sgr0)
PS1="\[$braket\][\$(parse_ip)\[$braket\]]:\[$workdir\]\w\[$gitbranch\]\$(parse_git_branch)\n\u\[$reset\]$ ";