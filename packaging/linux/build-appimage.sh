#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
WORKSPACE_ROOT=${ARCTIC_ROUTE_ROOT:-$(dirname -- "$PROJECT_ROOT")}
BUILD_ROOT="$PROJECT_ROOT/build/linux-x86_64"
VENV_ROOT="$BUILD_ROOT/venv"
ASSETS_ROOT="$BUILD_ROOT/runtime-assets"
DIST_ROOT="$BUILD_ROOT/dist"
APPDIR_ROOT="$BUILD_ROOT/Arctic_Route_Control_Center.AppDir"
RELEASE_ROOT="$PROJECT_ROOT/release"
OUTPUT="$RELEASE_ROOT/Arctic_Route_Control_Center-x86_64.AppImage"
APPIMAGETOOL_PATH=${APPIMAGETOOL:-"$BUILD_ROOT/tools/appimagetool-x86_64.AppImage"}
APPIMAGETOOL_SHA256=${APPIMAGETOOL_SHA256:-a6d71e2b6cd66f8e8d16c37ad164658985e0cf5fcaa950c90a482890cb9d13e0}
APPIMAGE_RUNTIME_PATH=${APPIMAGE_RUNTIME:-"$BUILD_ROOT/tools/runtime-x86_64"}
APPIMAGE_RUNTIME_SHA256=${APPIMAGE_RUNTIME_SHA256:-1cc49bcf1e2ccd593c379adb17c9f85a36d619088296504de95b1d06215aebbf}
ECCODES_PREFIX=${ARCTIC_ROUTE_ECCODES_PREFIX:-"$WORKSPACE_ROOT/work_package_a/.mamba-env"}
READY_PACKAGE=${ARCTIC_ROUTE_READY_PACKAGE:-"${XDG_DATA_HOME:-$HOME/.local/share}/arctic-route-control-center/artifacts/ready/winter-rebuilt-20260215-viewer-package-v4"}
DOWNLOAD_TOOL=0
SKIP_TESTS=0

for argument in "$@"; do
  case "$argument" in
    --download-appimagetool) DOWNLOAD_TOOL=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    *) echo "unknown argument: $argument" >&2; exit 2 ;;
  esac
done

test "$(uname -s)" = Linux || { echo "Linux build host required" >&2; exit 1; }
test "$(uname -m)" = x86_64 || { echo "x86_64 build host required" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }
test -f "$ECCODES_PREFIX/lib/libeccodes.so" || { echo "ecCodes Mamba prefix is incomplete: $ECCODES_PREFIX" >&2; exit 1; }
test -d "$ECCODES_PREFIX/share/eccodes/definitions" || { echo "ecCodes definitions are missing: $ECCODES_PREFIX" >&2; exit 1; }
for repository in arctic_route_contracts arctic_route_orchestrator work_package_a work_package_b work_package_c work_package_d; do
  git -C "$WORKSPACE_ROOT/$repository" rev-parse --git-dir >/dev/null 2>&1 || {
    echo "missing repository: $repository" >&2
    exit 1
  }
done

mkdir -p "$BUILD_ROOT" "$RELEASE_ROOT"
uv lock --directory "$PROJECT_ROOT"
uv lock --check --directory "$PROJECT_ROOT"
uv venv --clear --python 3.13 "$VENV_ROOT"
uv pip install --python "$VENV_ROOT/bin/python" "$PROJECT_ROOT" \
  'pyinstaller>=6.16,<7' 'pytest>=8.3,<10' 'ruff>=0.11,<1'

export ARCTIC_ROUTE_ROOT="$WORKSPACE_ROOT"
export ARCTIC_ROUTE_PRODUCTION_PACKAGE=1
export ARCTIC_ROUTE_ECCODES_PREFIX="$ECCODES_PREFIX"
export LD_LIBRARY_PATH="$ECCODES_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ECCODES_DEFINITION_PATH="$ECCODES_PREFIX/share/eccodes/definitions"
"$VENV_ROOT/bin/python" "$PROJECT_ROOT/scripts/prepare_runtime_assets.py" \
  --workspace-root "$WORKSPACE_ROOT" --output "$ASSETS_ROOT" \
  --ready-package "$READY_PACKAGE"
"$VENV_ROOT/bin/python" "$PROJECT_ROOT/scripts/scan_release.py" \
  --root "$ASSETS_ROOT" --workspace-root "$WORKSPACE_ROOT"
if test "$SKIP_TESTS" -eq 0; then
  "$VENV_ROOT/bin/python" -m pytest -q "$PROJECT_ROOT/tests"
fi

rm -rf -- "$DIST_ROOT" "$BUILD_ROOT/pyinstaller-work" "$APPDIR_ROOT"
export ARCTIC_ROUTE_BUILD_ASSETS="$ASSETS_ROOT"
"$VENV_ROOT/bin/python" -m PyInstaller --noconfirm --clean \
  --distpath "$DIST_ROOT" --workpath "$BUILD_ROOT/pyinstaller-work" \
  "$PROJECT_ROOT/packaging/arctic_route_control_center.spec"

find "$DIST_ROOT/arctic-route-control-center" -type f \
  \( -name direct_url.json -o -name uv_cache.json \) -delete
"$VENV_ROOT/bin/python" "$PROJECT_ROOT/scripts/sanitize_frozen_tree.py" \
  --root "$DIST_ROOT/arctic-route-control-center"

mkdir -p "$APPDIR_ROOT/usr/lib/arctic-route-control-center" "$APPDIR_ROOT/usr/share/icons/hicolor/scalable/apps"
cp -a "$DIST_ROOT/arctic-route-control-center/." "$APPDIR_ROOT/usr/lib/arctic-route-control-center/"
install -m 0755 "$PROJECT_ROOT/packaging/linux/AppRun" "$APPDIR_ROOT/AppRun"
install -m 0644 "$PROJECT_ROOT/packaging/linux/arctic-route-control-center.desktop" "$APPDIR_ROOT/arctic-route-control-center.desktop"
install -m 0644 "$PROJECT_ROOT/packaging/linux/arctic-route-control-center.svg" "$APPDIR_ROOT/arctic-route-control-center.svg"
install -m 0644 "$PROJECT_ROOT/packaging/linux/arctic-route-control-center.svg" \
  "$APPDIR_ROOT/usr/share/icons/hicolor/scalable/apps/arctic-route-control-center.svg"

env -u ARCTIC_ROUTE_ECCODES_PREFIX -u ECCODES_DEFINITION_PATH -u LD_LIBRARY_PATH \
  "$PROJECT_ROOT/scripts/verify_runtime.py" \
  --executable "$APPDIR_ROOT/usr/lib/arctic-route-control-center/arctic-route-control-center" \
  --artifact-root "$APPDIR_ROOT" --workspace-root "$WORKSPACE_ROOT"

if test ! -x "$APPIMAGETOOL_PATH"; then
  if test "$DOWNLOAD_TOOL" -ne 1; then
    echo "appimagetool missing. Set APPIMAGETOOL or pass --download-appimagetool." >&2
    exit 1
  fi
  mkdir -p "$(dirname -- "$APPIMAGETOOL_PATH")"
  env -u LD_LIBRARY_PATH curl --fail --location --proto '=https' --tlsv1.2 \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
    --output "$APPIMAGETOOL_PATH"
  chmod 0755 "$APPIMAGETOOL_PATH"
fi
actual_appimagetool_sha256=$(sha256sum "$APPIMAGETOOL_PATH" | awk '{print $1}')
test "$actual_appimagetool_sha256" = "$APPIMAGETOOL_SHA256" || {
  echo "appimagetool SHA256 mismatch: $actual_appimagetool_sha256" >&2
  exit 1
}
printf '%s  %s\n' "$actual_appimagetool_sha256" "$(basename -- "$APPIMAGETOOL_PATH")" \
  > "$APPIMAGETOOL_PATH.sha256-recorded"

if test ! -x "$APPIMAGE_RUNTIME_PATH"; then
  if test "$DOWNLOAD_TOOL" -ne 1; then
    echo "AppImage runtime missing. Set APPIMAGE_RUNTIME or pass --download-appimagetool." >&2
    exit 1
  fi
  env -u LD_LIBRARY_PATH curl --fail --location --proto '=https' --tlsv1.2 \
    https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
    --output "$APPIMAGE_RUNTIME_PATH"
  chmod 0755 "$APPIMAGE_RUNTIME_PATH"
fi
actual_runtime_sha256=$(sha256sum "$APPIMAGE_RUNTIME_PATH" | awk '{print $1}')
test "$actual_runtime_sha256" = "$APPIMAGE_RUNTIME_SHA256" || {
  echo "AppImage runtime SHA256 mismatch: $actual_runtime_sha256" >&2
  exit 1
}
printf '%s  %s\n' "$actual_runtime_sha256" "$(basename -- "$APPIMAGE_RUNTIME_PATH")" \
  > "$APPIMAGE_RUNTIME_PATH.sha256-recorded"

rm -f -- "$OUTPUT" "$OUTPUT.sha256"
env -u LD_LIBRARY_PATH ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 \
  "$APPIMAGETOOL_PATH" --runtime-file "$APPIMAGE_RUNTIME_PATH" "$APPDIR_ROOT" "$OUTPUT"
chmod 0755 "$OUTPUT"
(cd -- "$RELEASE_ROOT" && sha256sum "$(basename -- "$OUTPUT")" > "$(basename -- "$OUTPUT").sha256")
env -u ARCTIC_ROUTE_ECCODES_PREFIX -u ECCODES_DEFINITION_PATH -u LD_LIBRARY_PATH \
  ARCTIC_ROUTE_DATA_ROOT=$(mktemp -d) \
  "$OUTPUT" --appimage-extract-and-run --no-browser --self-test
echo "PASS: $OUTPUT"
