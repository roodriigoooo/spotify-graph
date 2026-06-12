#!/usr/bin/env bash
# Build the taste kernel to WASM for the browser.
#
# Output lands in frontend/public/kernel/ (web target, ES module) — vite copies public/
# into dist verbatim, so the kernel ships as a plain static asset and the loader fetches it
# at runtime from /kernel/. Without it, the frontend falls back to its pure-TS port of the
# same math. So this step is the "turn on the native kernel" switch, not a hard dependency.
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

OUT="../frontend/public/kernel"
# wasm-pack flags first; everything after `--` goes to cargo (the `wasm` feature gates the bindings)
wasm-pack build --release --target web --out-dir "$OUT" --out-name echoes_kernel -- --features wasm
echo "WASM kernel written to frontend/public/kernel/"
