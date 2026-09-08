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
DOWNLOAD_TOOL=0
SKIP_TESTS=0
# Viewer 数据制品由调用方显式声明（可重复 --viewer-package <目录>，或用
# --viewer-manifest <清单> / 环境变量 ARCTIC_ROUTE_VIEWER_PACKAGES）。不传则不
# 内嵌任何 Viewer 数据。
VIEWER_MANIFEST=${ARCTIC_ROUTE_VIEWER_MANIFEST:-}
VIEWER_PACKAGES=()

while [ $# -gt 0 ]; do
  case "$1" in
    --download-appimagetool) DOWNLOAD_TOOL=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --viewer-manifest)
      shift
      if [ $# -eq 0 ]; then echo "--viewer-manifest requires a file" >&2; exit 2; fi
      VIEWER_MANIFEST=$1; shift
      ;;
    --viewer-package)
      shift
      if [ $# -eq 0 ]; then echo "--viewer-package requires a directory" >&2; exit 2; fi
      VIEWER_PACKAGES+=("$1"); shift
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
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
declare -A source_repositories=(
  [arctic_route_control_center]="$PROJECT_ROOT"
  [arctic_route_contracts]="$WORKSPACE_ROOT/arctic_route_contracts"
  [arctic_route_orchestrator]="$WORKSPACE_ROOT/arctic_route_orchestrator"
  [work_package_a]="$WORKSPACE_ROOT/work_package_a"
  [work_package_b]="$WORKSPACE_ROOT/work_package_b"
  [work_package_c]="$WORKSPACE_ROOT/work_package_c"
  [work_package_d]="$WORKSPACE_ROOT/work_package_d"
)
for repository in "${!source_repositories[@]}"; do
  repo_path=${source_repositories[$repository]}
  branch=$(git -C "$repo_path" symbolic-ref --quiet --short HEAD) || {
    echo "detached Git worktree is not a release input: $repository" >&2
    exit 1
  }
  if test "$repository" = arctic_route_control_center && test "$branch" != main; then
    echo "Control Center must be on main (found $branch)" >&2
    exit 1
  fi
  if test "$repository" = work_package_d && test "$branch" != research-validation-system; then
    echo "work_package_d must be on research-validation-system (found $branch)" >&2
    exit 1
  fi
  if test -n "$(git -C "$repo_path" status --porcelain --untracked-files=all)"; then
    echo "dirty release worktree: $repository" >&2
    exit 1
  fi
done

mkdir -p "$BUILD_ROOT" "$RELEASE_ROOT"
uv lock --check --directory "$PROJECT_ROOT"
export UV_PROJECT_ENVIRONMENT="$VENV_ROOT"
uv sync --locked --python 3.13 --project "$PROJECT_ROOT" --group dev

export ARCTIC_ROUTE_ROOT="$WORKSPACE_ROOT"
export ARCTIC_ROUTE_PRODUCTION_PACKAGE=1
export ARCTIC_ROUTE_ECCODES_PREFIX="$ECCODES_PREFIX"
export LD_LIBRARY_PATH="$ECCODES_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ECCODES_DEFINITION_PATH="$ECCODES_PREFIX/share/eccodes/definitions"
viewer_args=(--workspace-root "$WORKSPACE_ROOT" --output "$ASSETS_ROOT")
if [ -n "$VIEWER_MANIFEST" ]; then
  viewer_args+=(--viewer-manifest "$VIEWER_MANIFEST")
fi
for package in "${VIEWER_PACKAGES[@]}"; do
  viewer_args+=(--viewer-package "$package")
done
"$VENV_ROOT/bin/python" "$PROJECT_ROOT/scripts/prepare_runtime_assets.py" \
  "${viewer_args[@]}"
"$VENV_ROOT/bin/python" "$PROJECT_ROOT/scripts/scan_release.py" \
  --root "$ASSETS_ROOT" --workspace-root "$WORKSPACE_ROOT"
if test "$SKIP_TESTS" -eq 0; then
  "$VENV_ROOT/bin/python" -m ruff check \
    "$PROJECT_ROOT/packaging" "$PROJECT_ROOT/scripts" \
    "$PROJECT_ROOT/src" "$PROJECT_ROOT/tests"
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

env -u ARCTIC_ROUTE_ROOT -u ARCTIC_ROUTE_PRODUCTION_PACKAGE \
  -u ARCTIC_ROUTE_ECCODES_PREFIX -u ECCODES_DEFINITION_PATH -u LD_LIBRARY_PATH \
  -u ARCTIC_ROUTE_DATA_ROOT -u ARCTIC_ROUTE_READY_PACKAGE -u ARCTIC_ROUTE_VIEWER_ROOT \
  -u ARCTIC_ROUTE_BUILD_ASSETS \
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
env -u ARCTIC_ROUTE_ROOT -u ARCTIC_ROUTE_PRODUCTION_PACKAGE \
  -u ARCTIC_ROUTE_ECCODES_PREFIX -u ECCODES_DEFINITION_PATH -u LD_LIBRARY_PATH \
  -u ARCTIC_ROUTE_READY_PACKAGE -u ARCTIC_ROUTE_VIEWER_ROOT -u ARCTIC_ROUTE_BUILD_ASSETS \
  ARCTIC_ROUTE_DATA_ROOT=$(mktemp -d) \
  "$OUTPUT" --appimage-extract-and-run --no-browser --self-test
echo "PASS: $OUTPUT"
