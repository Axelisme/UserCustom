#!/usr/bin/env bash
set -e

UserCustom=$(dirname $(dirname $(realpath "$0")))

# Installation resolves its source from this script's own path, so running it from a
# linked worktree would point every installed link at that worktree and leave the
# primary checkout's own tree littered with links back into it.  Refuse instead: the
# installed fleet must follow the persistence branch, not a task branch.
if git_dir=$(git -C "$UserCustom" rev-parse --git-dir 2>/dev/null); then
  common_dir=$(git -C "$UserCustom" rev-parse --git-common-dir)
  git_dir=$(realpath "$UserCustom/$git_dir" 2>/dev/null || realpath "$git_dir")
  common_dir=$(realpath "$UserCustom/$common_dir" 2>/dev/null || realpath "$common_dir")
  if [ "$git_dir" != "$common_dir" ]; then
    echo "error: setup must run from the primary checkout, not a linked worktree" >&2
    echo "       current: $UserCustom" >&2
    echo "       primary: $(dirname "$common_dir")" >&2
    exit 1
  fi
fi

# Old destinations are kept, never deleted.  Directory destinations cannot keep a
# `<name>.bak` sibling: the runtimes enumerate every entry of a skills directory, so
# the backup would be listed as a second, stale skill.  Retire those out of the tree.
BACKUP_ROOT="${USERCUSTOM_BACKUP_ROOT:-$HOME/.usercustom-backups}"

retire_directory_destination() {
  local dst=$1 relative target
  relative=${dst#"$HOME/"}
  target="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)/$relative"
  mkdir -p "$(dirname "$target")"
  echo "backup $dst -> $target"
  mv -T --backup=numbered -- "$dst" "$target"
}

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
        if [ -d "$dst" ]; then
          retire_directory_destination "$dst"
        else
          echo "backup $dst"
          mv -b -- "$dst" "$dst.bak"
        fi
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
orchestrate_destination_is_current() {
  local src=$1
  local dst=$2
  [ -e "$dst" ] && [ "$dst" -ef "$src" ]
}

replace_orchestrate_destination() {
  local src=$1
  local dst=$2
  [ -e "$src" ] || return 0
  if { [ -e "$dst" ] || [ -L "$dst" ]; } && orchestrate_destination_is_current "$src" "$dst"; then
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    # A skill destination lives inside a skills directory, whether it is a real
    # directory or a link to one; either way its backup must not stay there.
    if [ -d "$src" ]; then
      retire_directory_destination "$dst"
    else
      echo "backup $dst"
      mv -b -- "$dst" "$dst.bak"
    fi
  fi
  if [ -d "$src" ]; then
    ln -s "$src" "$dst"
  else
    ln "$src" "$dst"
  fi
  orchestrate_destination_is_current "$src" "$dst"
}

V119_SKILL_LAYOUTS=(.codex/skills .pi/agent/skills)
V119_SKILLS=(orchestrate code-review dev-flow planning-with-files to-spec to-tickets)
# Exact replacement is driven by the shipped source inventory, not a partial list of
# known identities.  Unrelated installed profiles remain managed by the generic copy.
V119_PROFILE_ROOTS=(.codex/agents .claude/agents .pi/agent/agents)
V119_STANDING_ORDER_PATHS=(.codex/AGENTS.md .pi/agent/APPEND_SYSTEM.md)

shipped_orchestrate_profile_inventory() {
  local root source relative
  for relative in "${V119_STANDING_ORDER_PATHS[@]}"; do
    source="$UserCustom/home/$relative"
    [ -f "$source" ] && printf '%s\n' "$relative"
  done
  for root in "${V119_PROFILE_ROOTS[@]}"; do
    [ -d "$UserCustom/home/$root" ] || continue
    while IFS= read -r source; do
      relative=${source#"$UserCustom/home/"}
      printf '%s\n' "$relative"
    done < <(find "$UserCustom/home/$root" -type f -print | sort)
  done
}

replace_current_orchestrate_destinations() {
  local skill layout relative
  for layout in "${V119_SKILL_LAYOUTS[@]}"; do
    for skill in "${V119_SKILLS[@]}"; do
      replace_orchestrate_destination "$UserCustom/home/$layout/$skill" "$HOME/$layout/$skill"
    done
  done
  replace_orchestrate_destination "$UserCustom/home/.claude/skills/orchestrate" "$HOME/.claude/skills/orchestrate"
  while IFS= read -r relative; do
    replace_orchestrate_destination "$UserCustom/home/$relative" "$HOME/$relative"
  done < <(shipped_orchestrate_profile_inventory)
}

remove_obsolete_orchestrate_profiles() {
  # Retire only exact legacy role identities after every shipped profile is installed.
  # A fixture or future release may legitimately ship one of these names, so never
  # retire a destination that is present in the source inventory.
  local runtime legacy relative source_relative destination ready
  for runtime in pi codex claude; do
    case "$runtime" in
      pi) legacy=(wave-reviewer.md integration-reviewer.md implementer.md python-module-reviewer.md); ready=.pi/agent/agents/wave-oracle.md ;;
      codex) legacy=(wave-reviewer.toml integration-reviewer.toml implementer.toml python-module-reviewer.toml); ready=.codex/agents/wave-oracle.toml ;;
      claude) legacy=(wave-reviewer.md integration-reviewer.md implementer.md python-module-reviewer.md); ready=.claude/agents/wave-oracle.md ;;
    esac
    [ -f "$UserCustom/home/$ready" ] || continue
    for relative in "${legacy[@]}"; do
      case "$runtime" in
        pi) source_relative=".pi/agent/agents/$relative" ;;
        codex) source_relative=".codex/agents/$relative" ;;
        claude) source_relative=".claude/agents/$relative" ;;
      esac
      if [ ! -f "$UserCustom/home/$source_relative" ]; then
        destination="$HOME/$source_relative"
        if [ -e "$destination" ] || [ -L "$destination" ]; then
          cp -a --backup=numbered -- "$destination" "$destination.bak"
        fi
        rm -f "$destination"
      fi
    done
  done
}

backup_cp "$UserCustom/home/.config" "$HOME/.config"
backup_cp "$UserCustom/home/.codex/skills" "$HOME/.codex/skills"
backup_cp "$UserCustom/home/.codex/agents" "$HOME/.codex/agents"
backup_cp_one "$UserCustom/home/.pi/agent/settings.json" "$HOME/.pi/agent/settings.json"
backup_cp "$UserCustom/home/.pi/agent/skills" "$HOME/.pi/agent/skills"
backup_cp "$UserCustom/home/.pi/agent/agents" "$HOME/.pi/agent/agents"
backup_cp "$UserCustom/home/.claude/skills" "$HOME/.claude/skills"
backup_cp "$UserCustom/home/.claude/agents" "$HOME/.claude/agents"
backup_cp "$UserCustom/home/.local/include" "$HOME/.local/include"

replace_current_orchestrate_destinations

# Backups written by earlier versions of this script are still sitting inside the
# skills directories, where every runtime lists them as extra skills.  They are the
# user's data, so report them and let the user decide; never delete them here.
report_stale_skill_backups() {
  local layout entry
  for layout in "${V119_SKILL_LAYOUTS[@]}" .claude/skills; do
    [ -d "$HOME/$layout" ] || continue
    for entry in "$HOME/$layout"/*.bak*; do
      { [ -e "$entry" ] || [ -L "$entry" ]; } || continue
      echo "notice: $entry is listed as a stale skill; remove it once the backup is no longer needed" >&2
    done
  done
}

validate_orchestrate_skill_destinations() {
  local layout skill source destination
  for layout in "${V119_SKILL_LAYOUTS[@]}"; do
    for skill in "${V119_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      destination="$HOME/$layout/$skill"
      [ -d "$source" ] || continue
      if [ ! -f "$source/SKILL.md" ] || [ ! -f "$destination/SKILL.md" ] \
        || ! orchestrate_destination_is_current "$source" "$destination"; then
        echo "error: unusable shipped v119 skill destination: $destination" >&2
        return 1
      fi
    done
  done
}

validate_orchestrate_profile_destinations() {
  local relative path
  while IFS= read -r relative; do
    path="$HOME/$relative"
    if [ ! -f "$path" ] || ! orchestrate_destination_is_current "$UserCustom/home/$relative" "$path"; then
      echo "error: unusable orchestrate destination (expected shipped identity): $path" >&2
      return 1
    fi
  done < <(shipped_orchestrate_profile_inventory)
}

# Retire the old identities only after every source tree has installed successfully and
# every replacement destination resolves to a usable regular profile file or skill.
validate_orchestrate_skill_destinations
validate_orchestrate_profile_destinations
remove_obsolete_orchestrate_profiles
report_stale_skill_backups
