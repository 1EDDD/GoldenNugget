#!/usr/bin/env bash
# Qt's official 6.12 frameworks target 14.4, but its Python binding wheel
# contains macOS 26 bindings. Rebuild both, never rewrite Mach-O minimums.
set -euo pipefail
qt_version=6.12.0
build_root="${RUNNER_TEMP:?}/goldennugget-qt"
qt_prefix="$build_root/Qt"
wheels="$PWD/.macos-qt-wheels"
mkdir -p "$build_root" "$wheels"
export MACOSX_DEPLOYMENT_TARGET=14.4
brew install cmake ninja llvm
export LLVM_INSTALL_DIR="$(brew --prefix llvm)"
python -m pip install --upgrade pip setuptools wheel packaging build numpy
python - <<'ARCH'
import os
import platform
expected = os.environ.get('BUILD_ARCH', platform.machine())
assert platform.machine() == expected, (platform.machine(), expected)
ARCH

for module in qtbase qtsvg; do
  git clone --depth 1 --branch "v${qt_version}" "https://github.com/qt/${module}.git" "$build_root/$module"
done
cmake -S "$build_root/qtbase" -B "$build_root/qtbase-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$qt_prefix" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET" \
  -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF \
  -DFEATURE_openssl=OFF -DFEATURE_dbus=OFF -DFEATURE_icu=OFF \
  -DFEATURE_zstd=OFF -DFEATURE_system_zlib=OFF \
  -DFEATURE_system_pcre2=OFF -DFEATURE_system_libpng=OFF \
  -DFEATURE_system_libjpeg=OFF -DFEATURE_system_freetype=OFF \
  -DFEATURE_system_harfbuzz=OFF
cmake --build "$build_root/qtbase-build" --parallel "$(sysctl -n hw.ncpu)"
cmake --install "$build_root/qtbase-build"
cmake -S "$build_root/qtsvg" -B "$build_root/qtsvg-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$qt_prefix" \
  -DCMAKE_INSTALL_PREFIX="$qt_prefix" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET" \
  -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
cmake --build "$build_root/qtsvg-build" --parallel "$(sysctl -n hw.ncpu)"
cmake --install "$build_root/qtsvg-build"
git clone --depth 1 --branch "v${qt_version}" \
  https://github.com/pyside/pyside-setup.git "$build_root/pyside-setup"
cd "$build_root/pyside-setup"
# This runtime-only Qt build has no Assistant/Designer/Linguist apps.
# PySide otherwise tries to install those bundles from qttools and fails.
# Resources and translations are already compiled and committed in src/qt.
python setup.py bdist_wheel --qtpaths="$qt_prefix/bin/qtpaths6" \
  --standalone --ignore-git --skip-docs --no-qt-tools \
  --module-subset=Core,Gui,Widgets,Network,Svg \
  --macos-deployment-target="$MACOSX_DEPLOYMENT_TARGET" \
  --parallel="$(sysctl -n hw.ncpu)"
# The generator is a build tool linked to host LLVM; never ship it.
for wheel in dist/*.whl; do
  case "$(basename "$wheel")" in
    shiboken6-[0-9]*.whl|[Pp]y[Ss]ide6-[0-9]*.whl) cp "$wheel" "$wheels/" ;;
  esac
done
python - "$wheels" <<'CHECK'
from pathlib import Path
import sys
from packaging.utils import parse_wheel_filename
names = {parse_wheel_filename(p.name)[0] for p in Path(sys.argv[1]).glob('*.whl')}
assert names == {'pyside6', 'shiboken6'}, names
CHECK
