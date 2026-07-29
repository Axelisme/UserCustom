#!/usr/bin/env bash
set -e

UserCustom=$(dirname "$(dirname "$(realpath "$0")")")

# Every question this script asks git is about *this* fleet, so only the repository
# whose toplevel is this source root may answer it.  `rev-parse --git-dir` alone would
# climb into an enclosing repository — an ordinary shape when $HOME is dotfile-managed
# or when the fleet is unpacked inside someone else's checkout — and that repository
# knows nothing about the fleet.  Resolve the answer once: it cannot change mid-run.
SOURCE_REPO=""
if source_toplevel=$(git -C "$UserCustom" rev-parse --show-toplevel 2>/dev/null) \
  && [ "$(realpath -- "$source_toplevel" 2>/dev/null)" = "$UserCustom" ]; then
  SOURCE_REPO=$UserCustom
fi

# Installation resolves its source from this script's own path, so running it from a
# linked worktree would point every installed link at that worktree and leave the
# primary checkout's own tree littered with links back into it.  Refuse instead: the
# installed fleet must follow the persistence branch, not a task branch.
if [ -n "$SOURCE_REPO" ]; then
  git_dir=$(git -C "$SOURCE_REPO" rev-parse --git-dir)
  common_dir=$(git -C "$SOURCE_REPO" rev-parse --git-common-dir)
  git_dir=$(realpath "$SOURCE_REPO/$git_dir" 2>/dev/null || realpath "$git_dir")
  common_dir=$(realpath "$SOURCE_REPO/$common_dir" 2>/dev/null || realpath "$common_dir")
  if [ "$git_dir" != "$common_dir" ]; then
    echo "error: setup must run from the primary checkout, not a linked worktree" >&2
    echo "       current: $UserCustom" >&2
    echo "       primary: $(dirname "$common_dir")" >&2
    exit 1
  fi
fi

# Non-current destinations are backed up before replacement. A directory destination
# cannot keep a `<name>.bak` sibling inside a skills directory because runtimes would
# enumerate the backup as another skill, so store it outside the installed tree.
BACKUP_ROOT="${USERCUSTOM_BACKUP_ROOT:-$HOME/.usercustom-backups}"
# One run is one restore point, so every directory backup shares one stamp.
BACKUP_STAMP=$(date +%Y%m%d-%H%M%S)
backup_directory_destination() {
  local dst=$1 relative target
  relative=${dst#"$HOME/"}
  target="$BACKUP_ROOT/$BACKUP_STAMP/$relative"
  mkdir -p "$(dirname "$target")"
  echo "backup $dst -> $target"
  mv -T --backup=numbered -- "$dst" "$target"
}

destination_matches_current_content() {
  local src=$1 dst=$2
  [ -L "$dst" ] && return 1
  [ -f "$src" ] && [ -f "$dst" ] && cmp -s -- "$src" "$dst"
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
        if destination_matches_current_content "$src" "$dst"; then
          rm -f -- "$dst"
        # Only a skills directory is enumerated entry by entry, so only there does a
        # sibling backup become a second, stale skill.  Everything else keeps it.
        elif [ -d "$dst" ] && [ "$(basename "$dst_dir")" = "skills" ]; then
          backup_directory_destination "$dst"
        else
          echo "backup $dst"
          if [ -d "$dst" ]; then
            # `mv -b` would move this directory *into* an existing `<name>.bak`
            # rather than replacing it, burying the older backup one level down.
            mv -T --backup=numbered -- "$dst" "$dst.bak"
          else
            mv -b -- "$dst" "$dst.bak"
          fi
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
      if destination_matches_current_content "$src" "$dst"; then
        rm -f -- "$dst"
      else
        echo "backup $dst"
        mv -b -- "$dst" "$dst.bak"
      fi
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
    if destination_matches_current_content "$src" "$dst"; then
      rm -f -- "$dst"
    # A skill destination lives inside a skills directory, whether it is a real
    # directory or a link to one; either way its backup must not stay there.
    elif [ -d "$src" ]; then
      backup_directory_destination "$dst"
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

CURRENT_SKILL_LAYOUTS=(.codex/skills .pi/agent/skills)
CURRENT_SKILLS=(orchestrate code-review dev-flow planning-with-files to-spec to-tickets)
# Exact replacement is driven by the shipped source inventory, not a partial list of
# known profile identities. Runtime assets remain an explicit allowlist so setup never
# scans, manages, or removes unrelated files in Pi's private extensions root.
CURRENT_PROFILE_ROOTS=(.codex/agents .claude/agents .pi/agent/agents)
CURRENT_STANDING_ORDER_PATHS=(.codex/AGENTS.md .pi/agent/APPEND_SYSTEM.md)
CURRENT_RUNTIME_ASSET_PATHS=(.pi/agent/extensions/orchestrate-pi.ts)

shipped_orchestrate_asset_inventory() {
  local root source relative
  for relative in "${CURRENT_STANDING_ORDER_PATHS[@]}"; do
    source="$UserCustom/home/$relative"
    [ -f "$source" ] && printf '%s\n' "$relative"
  done
  for root in "${CURRENT_PROFILE_ROOTS[@]}"; do
    [ -d "$UserCustom/home/$root" ] || continue
    while IFS= read -r source; do
      relative=${source#"$UserCustom/home/"}
      printf '%s\n' "$relative"
    done < <(find "$UserCustom/home/$root" -type f -print | sort)
  done
  # Required runtime assets are emitted even when missing so final validation
  # fails closed instead of silently producing an installation without them.
  printf '%s\n' "${CURRENT_RUNTIME_ASSET_PATHS[@]}"
}

replace_current_orchestrate_destinations() {
  local skill layout relative
  for layout in "${CURRENT_SKILL_LAYOUTS[@]}"; do
    for skill in "${CURRENT_SKILLS[@]}"; do
      replace_orchestrate_destination "$UserCustom/home/$layout/$skill" "$HOME/$layout/$skill"
    done
  done
  replace_orchestrate_destination "$UserCustom/home/.claude/skills/orchestrate" "$HOME/.claude/skills/orchestrate"
  while IFS= read -r relative; do
    replace_orchestrate_destination "$UserCustom/home/$relative" "$HOME/$relative"
  done < <(shipped_orchestrate_asset_inventory)
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


validate_orchestrate_skill_destinations() {
  local layout skill source destination
  for layout in "${CURRENT_SKILL_LAYOUTS[@]}"; do
    for skill in "${CURRENT_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      destination="$HOME/$layout/$skill"
      [ -d "$source" ] || continue
      if [ ! -f "$source/SKILL.md" ] || [ ! -f "$destination/SKILL.md" ] \
        || ! orchestrate_destination_is_current "$source" "$destination"; then
        echo "error: unusable shipped skill destination: $destination" >&2
        return 1
      fi
    done
  done
}

validate_orchestrate_asset_destinations() {
  local relative path
  while IFS= read -r relative; do
    path="$HOME/$relative"
    if [ ! -f "$path" ] || ! orchestrate_destination_is_current "$UserCustom/home/$relative" "$path"; then
      echo "error: unusable orchestrate destination (expected shipped identity): $path" >&2
      return 1
    fi
  done < <(shipped_orchestrate_asset_inventory)
}

# Validate every current destination after installation completes.
validate_orchestrate_skill_destinations
validate_orchestrate_asset_destinations
