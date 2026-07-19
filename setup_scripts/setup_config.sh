#!/usr/bin/env bash
set -e

UserCustom=$(dirname $(dirname $(realpath "$0")))

# setup config files
backup_cp() {
  src_dir=$1
  dst_dir=$2
  mkdir -p $dst_dir
  for src in $(realpath $src_dir/*); do
    dst=$dst_dir/$(basename $src)

    # if dst exists and not a link, backup it
    if [ -e $dst ]; then
      if [ ! -L $dst ]; then
        # same inode as src (still hard-linked) -> nothing to refresh
        if [ $dst -ef $src ]; then
          echo "skip $dst"
          continue
        fi
        echo "backup $dst"
        mv -b $dst $dst.bak
      else
        echo "skip $dst"
        continue
      fi
    fi

    # link src to dst
    if [ -d $src ]; then # is directory
      # soft link
      ln -Ts $src $dst
    else # is file
      # hard link
      ln $src $dst
    fi
  done
}

backup_cp_one() {
  src=$(realpath $1)
  dst=$2
  mkdir -p $(dirname $dst)
  if [ -e $dst ]; then
    if [ ! -L $dst ]; then
      if [ $dst -ef $src ]; then
        echo "skip $dst"
        return
      fi
      echo "backup $dst"
      mv -b $dst $dst.bak
    else
      echo "skip $dst"
      return
    fi
  fi
  ln $src $dst
}

backup_cp $UserCustom/home/.config $HOME/.config
backup_cp_one $UserCustom/home/.codex/AGENTS.md $HOME/.codex/AGENTS.md
backup_cp $UserCustom/home/.codex/skills $HOME/.codex/skills
backup_cp $UserCustom/home/.codex/agents $HOME/.codex/agents
backup_cp_one $UserCustom/home/.pi/agent/settings.json $HOME/.pi/agent/settings.json
backup_cp_one $UserCustom/home/.pi/agent/APPEND_SYSTEM.md $HOME/.pi/agent/APPEND_SYSTEM.md
backup_cp $UserCustom/home/.pi/agent/skills $HOME/.pi/agent/skills
backup_cp $UserCustom/home/.pi/agent/agents $HOME/.pi/agent/agents
backup_cp $UserCustom/home/.claude/skills $HOME/.claude/skills
backup_cp $UserCustom/home/.claude/agents $HOME/.claude/agents
backup_cp $UserCustom/home/.local/include $HOME/.local/include
