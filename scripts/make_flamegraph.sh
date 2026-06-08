#!/usr/bin/env bash
set -euo pipefail

DIR="/home/ubuntu/CWM-FDI/"
INPUT="${1:-out.perf}"
OUTPUT="${2:-flamegraph.svg}"

if [[ ! -f "$INPUT" ]]; then
  echo "Error: input file '$INPUT' not found." >&2
  exit 1
fi

# Find FlameGraph helper scripts either on PATH or in a local ./FlameGraph directory.
STACKCOLLAPSE="$(command -v stackcollapse-perf.pl || true)"
FLAMEGRAPH="$(command -v flamegraph.pl || true)"

if [[ -z "$STACKCOLLAPSE" && -x "$DIR/scripts/FlameGraph/stackcollapse-perf.pl" ]]; then
  STACKCOLLAPSE="$DIR/scripts/FlameGraph/stackcollapse-perf.pl"
fi

if [[ -z "$FLAMEGRAPH" && -x "$DIR/scripts/FlameGraph/flamegraph.pl" ]]; then
  FLAMEGRAPH="$DIR/scripts/FlameGraph/flamegraph.pl"
fi

if [[ -z "$STACKCOLLAPSE" || -z "$FLAMEGRAPH" ]]; then
  echo "Error: could not find FlameGraph scripts." >&2
  echo "Need stackcollapse-perf.pl and flamegraph.pl on PATH or in ./FlameGraph/" >&2
  exit 1
fi

tmp_stacks="$(mktemp)"
trap 'rm -f "$tmp_stacks"' EXIT

"$STACKCOLLAPSE" "$INPUT" > "$tmp_stacks"
"$FLAMEGRAPH" "$tmp_stacks" > "$OUTPUT"

echo "Wrote $OUTPUT"
