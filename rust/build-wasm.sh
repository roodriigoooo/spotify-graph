#!/usr/bin/env bash
# Build the taste kernel to WASM for the browser.
#
# Output lands in frontend/src/kernel/pkg/ (web target, ES module). The frontend's
# kernel loader (frontend/src/kernel.ts) picks it up automatically if present; without it,
# the frontend falls back to its pure-TS port of the same math. So this step is the
# "turn on the native kernel" switch, not a hard dependency.
#
# Prereqs (one-time):
#   cargo install wasm-pack
#   rustup target add wasm32-unknown-unknown
#
# Usage:
#   ./build-wasm.sh
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v wasm-pack >/dev/null 2>&1; then
  echo "wasm-pack not found. Install it with: cargo install wasm-pack" >&2
  exit 1
fi

OUT="../frontend/src/kernel/pkg"
wasm-pack build --release --target web --features wasm --out-dir "$OUT" --out-name echoes_kernel
echo "WASM kernel written to frontend/src/kernel/pkg/"
