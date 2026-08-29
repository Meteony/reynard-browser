#!/bin/sh

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
FIREFOX_DIR="$ROOT_DIR/.build/firefox"

REBUILD=false
case "${1:-}" in
	"") ;;
	--rebuild) REBUILD=true ;;
	*)
		echo "Usage: $0 [--rebuild]" >&2
		exit 2
		;;
esac

. "$ROOT_DIR/tools/xcode/use-xcode-26.2.sh"
. "$ROOT_DIR/tools/toolchains/release.env"

TARGET="$REYNARD_RUST_TARGET"
LLVM_PREFIX="${LLVM_PREFIX:-/opt/homebrew/opt/llvm}"
CC="${CC:-$LLVM_PREFIX/bin/clang}"
CXX="${CXX:-$LLVM_PREFIX/bin/clang++}"
HOST_CC="${HOST_CC:-$CC}"
HOST_CXX="${HOST_CXX:-$CXX}"

if [ ! -x "$CC" ] || [ ! -x "$CXX" ]; then
	echo "Missing pinned Clang toolchain under $LLVM_PREFIX." >&2
	exit 1
fi

# Keep Korboy's pinned LLVM for native iOS/host compilation. Do not set
# WASM_CC/WASM_CXX here: --enable-bootstrap supplies Mozilla's matching
# clang + WASI sysroot/compiler-rt pair for sandboxed WebAssembly libraries.
export CC CXX HOST_CC HOST_CXX
unset WASM_CC WASM_CXX || true
export RUSTUP_TOOLCHAIN="$REYNARD_RUST_TOOLCHAIN"

cd "$ROOT_DIR"

"$ROOT_DIR/tools/firefox/prepare-firefox.sh"

rm -f "$FIREFOX_DIR/.mozconfig"

{
	echo "ac_add_options --enable-application=mobile/ios"
	echo "ac_add_options --target=$TARGET"
	echo "ac_add_options --enable-ios-target=$REYNARD_DEPLOYMENT_TARGET"
	echo "ac_add_options --enable-webrtc"
	echo "ac_add_options --enable-optimize"
	echo "ac_add_options --disable-debug"
	echo "ac_add_options --disable-tests"
	echo "ac_add_options --enable-bootstrap"
} > "$FIREFOX_DIR/.mozconfig"

"$ROOT_DIR/tools/toolchains/validate-release-toolchain.sh" >/dev/null

GECKO_DIST="$FIREFOX_DIR/obj-aarch64-apple-ios/dist"
if [ "$REBUILD" = false ] &&
	REYNARD_PREPARED_VERIFIED=1 "$ROOT_DIR/tools/firefox/gecko-artifact-manifest.sh" check "$GECKO_DIST" >/dev/null 2>&1; then
	echo "Reusing Gecko artifacts for fingerprint $("$ROOT_DIR/tools/release/build-fingerprint.sh" gecko)."
	exit 0
fi

cd "$FIREFOX_DIR"
if [ "$REBUILD" = true ]; then
	./mach clobber
fi
./mach build

"$ROOT_DIR/tools/firefox/gecko-artifact-manifest.sh" write "$GECKO_DIST"
