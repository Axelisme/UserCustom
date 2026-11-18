#!/usr/bin/env bash
# Reserve the next decision number for an effort map and print it.
# Usage: bash next-decision-number.sh <map-dir> <writer-name>
# The number skips every NNNN already used in the map's decisions/ and retired/, in the archives
# under <map-dir>/../../archives/*/{decisions,retired}, and in earlier reservations. mkdir is
# atomic, so when several writers race, the one whose mkdir succeeds owns the number.
set -euo pipefail
map="${1:?map dir}"
who="${2:?writer name}"
reserve="$map/scratch/designer-coordination/decision-numbers"
mkdir -p "$reserve"
last=$( { for d in "$map/decisions" "$map/retired" "$reserve" \
                   "$map"/../../archives/*/decisions "$map"/../../archives/*/retired; do
            [ -d "$d" ] && ls "$d"
          done; } | grep -oE '^[0-9]{4}' | sort -n | tail -1 || true)
n=$((10#${last:-0} + 1))
until mkdir "$reserve/$(printf '%04d' "$n")" 2>/dev/null; do n=$((n + 1)); done
printf '%s\n' "$who" > "$reserve/$(printf '%04d' "$n")/owner"
printf '%04d\n' "$n"
