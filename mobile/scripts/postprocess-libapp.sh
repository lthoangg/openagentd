#!/usr/bin/env bash
#
# Post-process libapp.a for Xcode 27 / Swift 6 compatibility.
#
# On Xcode 27, SwiftPM internalizes @_cdecl functions in static library
# products (symbols become local 't'). While swift-rs attempts to promote
# symbols from the package's own module with llvm-objcopy, dependency modules
# like SwiftRs.o are excluded. As a result, _release_object, _retain_object,
# and _string_from_bytes remain local and the Xcode linker fails with
# undefined symbols.
#
# This script locates llvm-objcopy and marks those symbols as global (weak)
# in libapp.a before the final Xcode link step.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOBILE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRCROOT="${SRCROOT:-"$MOBILE_DIR/src-tauri/gen/apple"}"
CONFIGURATION="${CONFIGURATION:-Release}"
ARCHS="${ARCHS:-arm64}"

# Locate llvm-objcopy
OBJCOPY=""
if command -v llvm-objcopy >/dev/null 2>&1; then
  OBJCOPY="$(command -v llvm-objcopy)"
else
  RUSTC_SYSROOT="$(rustc --print sysroot 2>/dev/null || true)"
  if [ -n "$RUSTC_SYSROOT" ]; then
    HOST_ARCH="$(uname -m)"
    CANDIDATE="$RUSTC_SYSROOT/lib/rustlib/${HOST_ARCH}-apple-darwin/bin/llvm-objcopy"
    if [ -x "$CANDIDATE" ]; then
      OBJCOPY="$CANDIDATE"
    else
      rustup component add llvm-tools >/dev/null 2>&1 || true
      if [ -x "$CANDIDATE" ]; then
        OBJCOPY="$CANDIDATE"
      fi
    fi
  fi
fi

if [ -z "$OBJCOPY" ] || [ ! -x "$OBJCOPY" ]; then
  echo "postprocess-libapp: llvm-objcopy not found; skipping @_cdecl symbol globalization" >&2
  exit 0
fi

for arch in $ARCHS; do
  for config in "$CONFIGURATION" "${CONFIGURATION,,}" "${CONFIGURATION^}" release Release debug Debug; do
    LIB="$SRCROOT/Externals/$arch/$config/libapp.a"
    if [ -f "$LIB" ]; then
      "$OBJCOPY" \
        --globalize-symbol=_release_object --weaken-symbol=_release_object \
        --globalize-symbol=_retain_object --weaken-symbol=_retain_object \
        --globalize-symbol=_string_from_bytes --weaken-symbol=_string_from_bytes \
        "$LIB" 2>/dev/null || true
    fi
  done
done
