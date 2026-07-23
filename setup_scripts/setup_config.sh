#!/usr/bin/env bash
set -e

UserCustom=$(dirname $(dirname $(realpath "$0")))

# setup config files
backup_cp() {
  src_dir=$1
  dst_dir=$2
  [ -d "$src_dir" ] || return 0
  mkdir -p "$dst_dir"
  for src in "$src_dir"/*; do
    [ -e "$src" ] || continue
    dst=$dst_dir/$(basename "$src")

    # if dst exists and not a link, backup it
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      if [ ! -L "$dst" ]; then
        # same inode as src (still hard-linked) -> nothing to refresh
        if [ "$dst" -ef "$src" ]; then
          echo "skip $dst"
          continue
        fi
        echo "backup $dst"
        mv -b -- "$dst" "$dst.bak"
      else
        echo "skip $dst"
        continue
      fi
    fi

    # link src to dst
    if [ -d "$src" ]; then
      ln -Ts "$src" "$dst"
    else
      ln "$src" "$dst"
    fi
  done
}

backup_cp_one() {
  src=$(realpath "$1")
  dst=$2
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ]; then
    if [ ! -L "$dst" ]; then
      if [ "$dst" -ef "$src" ]; then
        echo "skip $dst"
        return
      fi
      echo "backup $dst"
      mv -b -- "$dst" "$dst.bak"
    else
      echo "skip $dst"
      return
    fi
  fi
  ln "$src" "$dst"
}

# The generic copy keeps user-managed links for unrelated assets. Orchestrate's
# shipped destinations are different: a stale link or regular copy must be
# replaced by the current UserCustom source, with the old destination retained
# as a backup before replacement.
replace_orchestrate_destination() {
  local src=$1
  local dst=$2
  [ -e "$src" ] || return 0
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    if [ -d "$src" ]; then
      if [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
        return 0
      fi
    elif [ "$dst" -ef "$src" ]; then
      return 0
    fi
    echo "backup $dst"
    mv -b -- "$dst" "$dst.bak"
  fi
  if [ -d "$src" ]; then
    ln -s "$src" "$dst"
  else
    ln "$src" "$dst"
  fi

  if [ -d "$src" ]; then
    [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]
  else
    [ "$dst" -ef "$src" ] && cmp -s "$dst" "$src"
  fi
}

replace_current_orchestrate_destinations() {
  replace_orchestrate_destination "$UserCustom/home/.codex/skills/orchestrate" "$HOME/.codex/skills/orchestrate"
  replace_orchestrate_destination "$UserCustom/home/.pi/agent/skills/orchestrate" "$HOME/.pi/agent/skills/orchestrate"
  replace_orchestrate_destination "$UserCustom/home/.claude/skills/orchestrate" "$HOME/.claude/skills/orchestrate"
  replace_orchestrate_destination "$UserCustom/home/.codex/agents/wave-oracle.toml" "$HOME/.codex/agents/wave-oracle.toml"
  replace_orchestrate_destination "$UserCustom/home/.codex/agents/wave-implementer.toml" "$HOME/.codex/agents/wave-implementer.toml"
  replace_orchestrate_destination "$UserCustom/home/.pi/agent/agents/wave-oracle.md" "$HOME/.pi/agent/agents/wave-oracle.md"
  replace_orchestrate_destination "$UserCustom/home/.pi/agent/agents/wave-implementer.md" "$HOME/.pi/agent/agents/wave-implementer.md"
  replace_orchestrate_destination "$UserCustom/home/.claude/agents/wave-oracle.md" "$HOME/.claude/agents/wave-oracle.md"
  replace_orchestrate_destination "$UserCustom/home/.claude/agents/wave-implementer.md" "$HOME/.claude/agents/wave-implementer.md"
}

remove_obsolete_orchestrate_profiles() {
  # Retire only exact legacy role identities after every v119 role is installed.
  if [ -e "$UserCustom/home/.pi/agent/agents/wave-oracle.md" ]; then
    rm -f "$HOME/.pi/agent/agents/wave-reviewer.md" "$HOME/.pi/agent/agents/integration-reviewer.md"
  fi
  if [ -e "$UserCustom/home/.codex/agents/wave-oracle.toml" ]; then
    rm -f "$HOME/.codex/agents/wave-reviewer.toml" "$HOME/.codex/agents/integration-reviewer.toml"
  fi
  if [ -e "$UserCustom/home/.claude/agents/wave-oracle.md" ]; then
    rm -f "$HOME/.claude/agents/wave-reviewer.md" "$HOME/.claude/agents/integration-reviewer.md"
  fi
}

backup_cp "$UserCustom/home/.config" "$HOME/.config"
backup_cp_one "$UserCustom/home/.codex/AGENTS.md" "$HOME/.codex/AGENTS.md"
backup_cp "$UserCustom/home/.codex/skills" "$HOME/.codex/skills"
backup_cp "$UserCustom/home/.codex/agents" "$HOME/.codex/agents"
backup_cp_one "$UserCustom/home/.pi/agent/settings.json" "$HOME/.pi/agent/settings.json"
backup_cp_one "$UserCustom/home/.pi/agent/APPEND_SYSTEM.md" "$HOME/.pi/agent/APPEND_SYSTEM.md"
backup_cp "$UserCustom/home/.pi/agent/skills" "$HOME/.pi/agent/skills"
backup_cp "$UserCustom/home/.pi/agent/agents" "$HOME/.pi/agent/agents"
backup_cp "$UserCustom/home/.claude/skills" "$HOME/.claude/skills"
backup_cp "$UserCustom/home/.claude/agents" "$HOME/.claude/agents"
backup_cp "$UserCustom/home/.local/include" "$HOME/.local/include"

replace_current_orchestrate_destinations

validate_orchestrate_profile_destinations() {
  local path
  for path in \
    "$HOME/.pi/agent/agents/wave-oracle.md" \
    "$HOME/.pi/agent/agents/wave-implementer.md" \
    "$HOME/.codex/agents/wave-oracle.toml" \
    "$HOME/.codex/agents/wave-implementer.toml" \
    "$HOME/.claude/agents/wave-oracle.md" \
    "$HOME/.claude/agents/wave-implementer.md"; do
    if [ ! -f "$path" ]; then
      echo "error: unusable wave profile destination (expected regular file): $path" >&2
      return 1
    fi
  done
}

# Retire the old identities only after every source tree has installed successfully and
# every replacement destination resolves to a usable regular profile file.
validate_orchestrate_profile_destinations
remove_obsolete_orchestrate_profiles
