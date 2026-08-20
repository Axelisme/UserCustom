#!/usr/bin/env bash
set -euo pipefail

repo_root=$(dirname "$(dirname "$(realpath "$0")")")

backup_existing() {
  local destination=$1
  local backup="${destination}.bak"

  echo "backup $destination -> $backup"
  mv -T --backup=numbered -- "$destination" "$backup"
}

link_with_backup() {
  local source=$1 destination=$2

  [ -e "$source" ] || return 0
  mkdir -p "$(dirname "$destination")"

  if [ -e "$destination" ] || [ -L "$destination" ]; then
    if [ -e "$destination" ] && [ "$destination" -ef "$source" ]; then
      echo "skip $destination"
      return 0
    fi
    backup_existing "$destination"
  fi

  echo "link $destination -> $source"
  ln -s -- "$source" "$destination"
}

link_directory_contents() {
  local source_directory=$1 destination_directory=$2 source

  [ -d "$source_directory" ] || return 0
  if [ -L "$destination_directory" ] || { [ -e "$destination_directory" ] && [ ! -d "$destination_directory" ]; }; then
    backup_existing "$destination_directory"
  fi
  mkdir -p "$destination_directory"

  shopt -s dotglob nullglob
  for source in "$source_directory"/*; do
    link_with_backup "$source" "$destination_directory/$(basename "$source")"
  done
}

disable_legacy_entry() {
  local active=$1 disabled=$2

  if [ ! -e "$active" ] && [ ! -L "$active" ]; then
    return 0
  fi
  mkdir -p "$(dirname "$disabled")"
  if [ -e "$disabled" ] || [ -L "$disabled" ]; then
    backup_existing "$disabled"
  fi
  echo "disable $active -> $disabled"
  mv -T -- "$active" "$disabled"
}

for profile in acceptance-reviewer lane-worker; do
  disable_legacy_entry "$HOME/.codex/agents/$profile.toml" "$HOME/.codex/disabled-agents/$profile.toml.bak"
  disable_legacy_entry "$HOME/.pi/agent/agents/$profile.md" "$HOME/.pi/agent/disabled-agents/$profile.md.bak"
  disable_legacy_entry "$HOME/.claude/agents/$profile.md" "$HOME/.claude/disabled-agents/$profile.md.bak"
done
disable_legacy_entry \
  "$HOME/.pi/agent/agents/mcp-skill-tester.md" \
  "$HOME/.pi/agent/disabled-agents/mcp-skill-tester.md.bak"

for relative in \
  .config \
  .codex/skills \
  .codex/agents \
  .pi/agent/skills \
  .pi/agent/extensions \
  .pi/agent/agents \
  .claude/skills \
  .claude/agents \
  .local/include; do
  link_directory_contents "$repo_root/home/$relative" "$HOME/$relative"
done

for relative in \
  .pi/settings.json \
  .pi/agent/settings.json \
  .pi/acp.json \
  .codex/AGENTS.md \
  .pi/agent/APPEND_SYSTEM.md; do
  link_with_backup "$repo_root/home/$relative" "$HOME/$relative"
done
