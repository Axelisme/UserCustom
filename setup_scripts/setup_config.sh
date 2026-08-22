#!/usr/bin/env bash
# 每個安裝項目輸出一行狀態；單項失敗只記錄不中止，最後才一次回報。
set -uo pipefail
shopt -s dotglob nullglob

repo=$(dirname "$(dirname "$(realpath "$0")")")
tree="$repo/home"
failed=0

# 從 linked worktree 安裝會把 $HOME 的設定指向那棵暫時的樹。
if git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
  if [ "$(git -C "$repo" rev-parse --git-dir)" != "$(git -C "$repo" rev-parse --git-common-dir)" ]; then
    echo "setup_config: refusing to install from a linked worktree: $repo" >&2
    exit 1
  fi
fi

short() {
  case "$1" in
    "$HOME"/*) echo "~${1#"$HOME"}" ;;
    "$repo"/*) echo "${1#"$repo"/}" ;;
    *) echo "$1" ;;
  esac
}

# 一個安裝項目的計數與明細，由 begin 重置、report_* 印出。
begin() { item=$1 single=$2; ok=0 linked=0 backed=0 pruned=0 broken=0; detail=(); }
note() { detail+=("$1"); }

flush() {
  local line
  for line in "${detail[@]}"; do printf '    %s\n' "$line"; done
  [ "$broken" -gt 0 ] && failed=$((failed + 1))
  return 0
}

# 目錄項目：一行計數，底下逐條列出真正動過的東西。
report_each() {
  local parts=()
  [ "$ok" -gt 0 ] && parts+=("$ok unchanged")
  [ "$linked" -gt 0 ] && parts+=("$linked linked")
  [ "$backed" -gt 0 ] && parts+=("$backed backed up")
  [ "$pruned" -gt 0 ] && parts+=("$pruned pruned")
  [ "$broken" -gt 0 ] && parts+=("$broken FAILED")
  [ "${#parts[@]}" -eq 0 ] && parts+=("empty")
  printf '%-27s %s\n' "$item" "$(IFS=,; echo "${parts[*]}" | sed 's/,/, /g')"
  flush
}

# 單一路徑項目：狀態直接是一個詞，不必數數。
report_one() {
  local word=unchanged
  [ "$linked" -gt 0 ] && word=linked
  [ "$backed" -gt 0 ] && word="backed up + linked"
  [ "$broken" -gt 0 ] && word=FAILED
  printf '%-27s %s\n' "$item" "$word"
  flush
}

link() {
  local source=$1 dest=$2 current target n=1
  if [ ! -e "$source" ] && [ ! -L "$source" ]; then
    broken=$((broken + 1)); note "missing source  $(short "$source")"; return
  fi

  if [ -L "$dest" ]; then
    current=$(readlink "$dest")
    if [ "$current" = "$source" ]; then
      ok=$((ok + 1)); return
    fi
    if [[ "$current" == "$tree"/* ]]; then
      rm -- "$dest"  # 我方的舊 link，沒有內容值得備份
    fi
  fi

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    target="$dest.bak"
    while [ -e "$target" ] || [ -L "$target" ]; do target="$dest.bak.$((n++))"; done
    if ! mv -T -- "$dest" "$target" 2>/dev/null; then
      broken=$((broken + 1)); note "cannot back up  $(short "$dest")"; return
    fi
    backed=$((backed + 1)); note "backup  $(short "$dest") -> $(short "$target")"
  fi

  mkdir -p "$(dirname "$dest")"
  if ln -s -- "$source" "$dest" 2>/dev/null; then
    linked=$((linked + 1))
    [ "$single" = no ] && note "link  $(short "$dest") -> $(short "$source")"
  else
    broken=$((broken + 1)); note "cannot link  $(short "$dest")"
  fi
  return 0
}

# 來源已從 repo 移除的我方 link 會留成孤兒，重跑也清不掉，所以先收。
prune() {
  local dir=$1 entry target
  for entry in "$dir"/*; do
    [ -L "$entry" ] || continue
    target=$(readlink "$entry")
    [[ "$target" == "$tree"/* ]] || continue
    if [ -e "$target" ] || [ -L "$target" ]; then continue; fi
    if rm -- "$entry" 2>/dev/null; then
      pruned=$((pruned + 1)); note "prune  $(short "$entry")"
    else
      broken=$((broken + 1)); note "cannot prune  $(short "$entry")"
    fi
  done
}

# 目錄底下每個 entry 各裝一條 link。
link_each() {
  local source="$tree/$1" dest="$HOME/$1" entry
  begin "$1" no
  if [ ! -d "$source" ]; then
    broken=$((broken + 1)); note "missing source directory  $(short "$source")"
    report_each; return
  fi
  mkdir -p "$dest"
  prune "$dest"
  for entry in "$source"/*; do
    link "$entry" "$dest/${entry##*/}"
  done
  report_each
}

# 這個 path 本身裝一條 link。
link_one() {
  begin "$1" yes
  link "$tree/$1" "$HOME/$1"
  report_one
}

# ---- 安裝項目：一行一個，註解掉即停裝 ----------------------------------

# 一般設定
link_each .config
link_each .local/include

# Codex
link_each .codex/skills
link_each .codex/agents
link_one  .codex/AGENTS.md

# Pi
link_each .pi/agent/skills
link_each .pi/agent/agents
link_each .pi/agent/extensions
link_one  .pi/settings.json
link_one  .pi/agent/settings.json
link_one  .pi/agent/APPEND_SYSTEM.md
link_one  .pi/acp.json

# Claude
link_each .claude/skills
link_each .claude/agents
link_each .claude/workflows

# ------------------------------------------------------------------------

if [ "$failed" -gt 0 ]; then
  echo "setup_config: $failed item(s) failed" >&2
  exit 1
fi
