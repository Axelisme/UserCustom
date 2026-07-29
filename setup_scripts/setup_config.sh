#!/usr/bin/env bash
set -e

UserCustom=$(dirname "$(dirname "$(realpath "$0")")")
CURRENT_SKILL_LAYOUTS=(.codex/skills .pi/agent/skills)
CLAUDE_SKILL_LAYOUT=.claude/skills
ACTIVE_LIFECYCLE_SKILLS=(orchestrate dev-flow wayfinder to-spec to-tickets prototype candidate-backlog)
RETIRED_LIFECYCLE_SKILLS=(planning-with-files)
CURRENT_PROFILE_ROOTS=(.codex/agents .claude/agents .pi/agent/agents)
CURRENT_STANDING_ORDER_PATHS=(.codex/AGENTS.md .pi/agent/APPEND_SYSTEM.md)
CURRENT_RUNTIME_ASSET_PATHS=(.pi/agent/extensions/orchestrate-pi.ts)

SOURCE_REPO=""
if source_toplevel=$(git -C "$UserCustom" rev-parse --show-toplevel 2>/dev/null) \
  && [ "$(realpath -- "$source_toplevel" 2>/dev/null)" = "$UserCustom" ]; then
  SOURCE_REPO=$UserCustom
fi
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

BACKUP_ROOT="${USERCUSTOM_BACKUP_ROOT:-$HOME/.usercustom-backups}"
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

backup_cp() {
  local src_dir=$1 dst_dir=$2 src dst
  [ -d "$src_dir" ] || return 0
  mkdir -p "$dst_dir"
  for src in "$src_dir"/*; do
    [ -e "$src" ] || continue
    dst="$dst_dir/$(basename "$src")"
    if [ -e "$dst" ] || [ -L "$dst" ]; then
      if [ ! -L "$dst" ]; then
        if [ "$dst" -ef "$src" ]; then
          echo "skip $dst"
          continue
        fi
        if destination_matches_current_content "$src" "$dst"; then
          rm -f -- "$dst"
        elif [ -d "$dst" ] && [ "$(basename "$dst_dir")" = "skills" ]; then
          backup_directory_destination "$dst"
        else
          echo "backup $dst"
          if [ -d "$dst" ]; then
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
    if [ -d "$src" ]; then
      ln -Ts "$src" "$dst"
    else
      ln "$src" "$dst"
    fi
  done
}

backup_cp_one() {
  local src dst
  src=$(realpath "$1")
  dst=$2
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
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

destination_is_current() {
  local src=$1 dst=$2
  [ -e "$dst" ] && [ "$dst" -ef "$src" ]
}

replace_destination() {
  local src=$1 dst=$2
  [ -e "$src" ] || return 0
  if { [ -e "$dst" ] || [ -L "$dst" ]; } && destination_is_current "$src" "$dst"; then
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    if destination_matches_current_content "$src" "$dst"; then
      rm -f -- "$dst"
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
  destination_is_current "$src" "$dst"
}

is_named() {
  local candidate=$1 entry
  shift
  for entry in "$@"; do
    [ "$candidate" = "$entry" ] && return 0
  done
  return 1
}

all_skill_layouts() {
  printf '%s\n' "${CURRENT_SKILL_LAYOUTS[@]}" "$CLAUDE_SKILL_LAYOUT"
}

unrelated_source_skills() {
  local layout=$1 source name
  source="$UserCustom/home/$layout"
  [ -d "$source" ] || return 0
  for source in "$source"/*; do
    [ -e "$source" ] || continue
    name=$(basename "$source")
    is_named "$name" "${ACTIVE_LIFECYCLE_SKILLS[@]}" && continue
    is_named "$name" "${RETIRED_LIFECYCLE_SKILLS[@]}" && continue
    printf '%s\n' "$name"
  done | sort
}

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
  printf '%s\n' "${CURRENT_RUNTIME_ASSET_PATHS[@]}"
}

preflight_sources() {
  local layout skill source relative
  while IFS= read -r layout; do
    for skill in "${ACTIVE_LIFECYCLE_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      if [ ! -f "$source/SKILL.md" ]; then
        echo "error: setup preflight found unusable shipped skill: $source" >&2
        return 1
      fi
    done
    for skill in "${RETIRED_LIFECYCLE_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      if [ ! -f "$source/SKILL.md" ]; then
        echo "error: setup preflight found unusable retired capsule: $source" >&2
        return 1
      fi
    done
  done < <(all_skill_layouts)
  for relative in \
    home/.codex/skills/dev-flow/scripts/plan.py \
    home/.codex/skills/dev-flow/templates/INDEX.md \
    home/.codex/skills/dev-flow/templates/ticket.md \
    home/.codex/skills/planning-with-files/scripts/plan.py \
    home/.codex/skills/planning-with-files/templates/INDEX.md; do
    if [ ! -f "$UserCustom/$relative" ]; then
      echo "error: setup preflight missing required source: $relative" >&2
      return 1
    fi
  done
  while IFS= read -r relative; do
    if [ ! -f "$UserCustom/home/$relative" ]; then
      echo "error: setup preflight missing required source: $relative" >&2
      return 1
    fi
  done < <(shipped_orchestrate_asset_inventory)
}

retired_destination_is_managed() {
  local source=$1 destination=$2
  [ -L "$destination" ] && [ -e "$destination" ] && [ "$destination" -ef "$source" ]
}

preflight_retired_destinations() {
  local layout skill source destination
  while IFS= read -r layout; do
    for skill in "${RETIRED_LIFECYCLE_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      destination="$HOME/$layout/$skill"
      if [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
        continue
      fi
      if ! retired_destination_is_managed "$source" "$destination"; then
        echo "error: foreign retired destination; setup made no changes: $destination" >&2
        return 1
      fi
    done
  done < <(all_skill_layouts)
}

smoke_task_record() {
  local plan=$1 smoke_root
  smoke_root=$(mktemp -d "${TMPDIR:-/tmp}/usercustom-task-record.XXXXXX")
  if ! (cd "$smoke_root" \
    && python "$plan" create setup-smoke --goal "Verify durable task replacement." >/dev/null \
    && python "$plan" check setup-smoke >/dev/null); then
    rm -rf -- "$smoke_root"
    echo "error: replacement smoke failed; retired planning destinations were not changed" >&2
    return 1
  fi
  rm -rf -- "$smoke_root"
}

install_skill_inventory() {
  local layout skill
  while IFS= read -r layout; do
    for skill in "${ACTIVE_LIFECYCLE_SKILLS[@]}"; do
      replace_destination "$UserCustom/home/$layout/$skill" "$HOME/$layout/$skill"
    done
    while IFS= read -r skill; do
      replace_destination "$UserCustom/home/$layout/$skill" "$HOME/$layout/$skill"
    done < <(unrelated_source_skills "$layout")
  done < <(all_skill_layouts)
}

install_orchestrate_assets() {
  local relative
  while IFS= read -r relative; do
    replace_destination "$UserCustom/home/$relative" "$HOME/$relative"
  done < <(shipped_orchestrate_asset_inventory)
}

validate_active_destinations() {
  local layout skill source destination relative
  while IFS= read -r layout; do
    for skill in "${ACTIVE_LIFECYCLE_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      destination="$HOME/$layout/$skill"
      if [ ! -f "$destination/SKILL.md" ] || ! destination_is_current "$source" "$destination"; then
        echo "error: unusable shipped skill destination: $destination" >&2
        return 1
      fi
    done
  done < <(all_skill_layouts)
  while IFS= read -r relative; do
    if [ ! -f "$HOME/$relative" ] \
      || ! destination_is_current "$UserCustom/home/$relative" "$HOME/$relative"; then
      echo "error: unusable orchestrate destination (expected shipped identity): $HOME/$relative" >&2
      return 1
    fi
  done < <(shipped_orchestrate_asset_inventory)
  if [ ! "$HOME/.pi/agent/skills/dev-flow/scripts/plan.py" -ef \
       "$UserCustom/home/.codex/skills/dev-flow/scripts/plan.py" ]; then
    echo "error: unusable Pi task-record replacement identity" >&2
    return 1
  fi
}

remove_retired_destinations() {
  local layout skill source destination failed=0
  local -a removed=() remaining=()
  while IFS= read -r layout; do
    for skill in "${RETIRED_LIFECYCLE_SKILLS[@]}"; do
      source="$UserCustom/home/$layout/$skill"
      destination="$HOME/$layout/$skill"
      if [ ! -e "$destination" ] && [ ! -L "$destination" ]; then
        continue
      fi
      if retired_destination_is_managed "$source" "$destination" && rm -f -- "$destination"; then
        removed+=("$destination")
      else
        remaining+=("$destination")
        failed=1
      fi
    done
  done < <(all_skill_layouts)
  if [ "$failed" -ne 0 ]; then
    echo "error: retired removal incomplete; replacement remains usable" >&2
    printf 'removed: %s\n' "${removed[@]}" >&2
    printf 'remaining: %s\n' "${remaining[@]}" >&2
    echo "rerun the normal setup command after correcting removal" >&2
    return 1
  fi
}

validate_retired_absent() {
  local layout skill destination failed=0
  while IFS= read -r layout; do
    for skill in "${RETIRED_LIFECYCLE_SKILLS[@]}"; do
      destination="$HOME/$layout/$skill"
      if [ -e "$destination" ] || [ -L "$destination" ]; then
        echo "error: retired destination remains: $destination" >&2
        failed=1
      fi
    done
  done < <(all_skill_layouts)
  [ "$failed" -eq 0 ]
}

verify_installed_orchestrate_releases() {
  local codex_skill pi_skill result
  codex_skill="$HOME/.codex/skills/orchestrate"
  pi_skill="$HOME/.pi/agent/skills/orchestrate"

  if ! result=$(python "$codex_skill/scripts/orchestrate.py" \
    --skill-dir "$codex_skill" doctor); then
    printf '%s\n' "$result" >&2
    echo "error: Codex v136 release verification failed; retired planning destinations were not changed" >&2
    return 1
  fi

  if ! result=$(python - "$codex_skill/scripts" "$pi_skill" <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from _orchestrate.release import verify_release

result = verify_release(Path(sys.argv[2]))
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if result["ok"] else 1)
PY
  ); then
    printf '%s\n' "$result" >&2
    echo "error: Pi v136 release verification failed; retired planning destinations were not changed" >&2
    return 1
  fi
}

# Every operation above this boundary is read-only with respect to HOME.
preflight_sources
preflight_retired_destinations
smoke_task_record "$UserCustom/home/.codex/skills/dev-flow/scripts/plan.py"

backup_cp "$UserCustom/home/.config" "$HOME/.config"
backup_cp "$UserCustom/home/.codex/agents" "$HOME/.codex/agents"
backup_cp_one "$UserCustom/home/.pi/agent/settings.json" "$HOME/.pi/agent/settings.json"
backup_cp "$UserCustom/home/.pi/agent/agents" "$HOME/.pi/agent/agents"
backup_cp "$UserCustom/home/.claude/agents" "$HOME/.claude/agents"
backup_cp "$UserCustom/home/.local/include" "$HOME/.local/include"
install_skill_inventory
install_orchestrate_assets
validate_active_destinations
smoke_task_record "$HOME/.codex/skills/dev-flow/scripts/plan.py"
verify_installed_orchestrate_releases
remove_retired_destinations
validate_retired_absent
validate_active_destinations
smoke_task_record "$HOME/.codex/skills/dev-flow/scripts/plan.py"
printf 'active lifecycle: %s\n' "${ACTIVE_LIFECYCLE_SKILLS[*]}"
printf 'retired lifecycle removed: %s\n' "${RETIRED_LIFECYCLE_SKILLS[*]}"
