#!/usr/bin/env bash
# This file is part of the project-reforged-linux Project.
# License: GPL-3.0-or-later. Contact: project-reforged-linux@trinity2k.net
# Additional terms under GPLv3 section 7(b): see NOTICE.
#
# Builds the launcher's release artifacts into dist/.
#
# Usage:
#   tools/build.sh [arch]           build in an Arch Linux container (podman), then run the
#                                   gates here on the host (default)
#   tools/build.sh appimage         build on this machine as it is
#   tools/build.sh suite            the test suite on the image's Python, after appimage
#   tools/build.sh check FILE       the run gates on an AppImage built earlier
#
# Environment:
#   RELEASE=1      tagged release from an unmodified tree: no git stamp in the file name
#   WINE_TARBALL   a local copy of the pinned Wine build (checked against WINE_SHA256)
#   PYTHON         appimage and suite only: interpreter for the venv and the image
#                  (default: python3; the arch target uses the container's)
#   TOOLS_CACHE    appimage only: where the downloaded build tools are kept
#                  (default: build/tools)
#   SQFS_COMP_LEVEL  zstd level for the squashfs (default: 15)
#   SKIP_RUN_GATES=1 pack without starting the image, for a host with no FUSE and no session
#
# The image is meant to be built on an up-to-date Arch Linux; any other build host
# makes a development image only (build-info.txt records which one it was).
#
# Pipelines stay on: every tool here signals failure by exit code, none by warning.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

readonly ARTIFACT_NAME="project-reforged-linux-launcher"
readonly BUILD_IMAGE="localhost/project-reforged-linux-build:arch"
readonly PACKAGE="project_reforged_linux"
readonly GATE_TOOLS=(Xvfb xprop xwininfo readelf)
readonly PYTEST_VERSION="9.2.0"
# Files every copy of the image carries at its top, beside SYSTEM-LIBRARIES.txt.
readonly LICENSE_FILES=(LICENSE NOTICE THIRD_PARTY_LICENSES.txt)

# Pinned build tools. quick-sharun pins and checks its own downloads (sharun, helpers).
readonly QUICK_SHARUN_COMMIT="a159da2858637fc3e8c480581b2999640ebbfe30"
readonly QUICK_SHARUN_URL="https://raw.githubusercontent.com/pkgforge-dev/Anylinux-AppImages/${QUICK_SHARUN_COMMIT}/useful-tools/quick-sharun.sh"
readonly QUICK_SHARUN_SHA256="6fc4f4561288297a7f8237f92b872656be1b7a4ba534f2b6cb9cfecabcddfd9d"
readonly URUNTIME_URL="https://github.com/VHSgunzo/uruntime/releases/download/v0.8.3/uruntime-appimage-squashfs-x86_64"
readonly URUNTIME_SHA256="5728431f05efb4425239aafdd48f206db5d9b1ca2e476c8c463db5fe75badb32"
readonly APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
readonly APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

# The bundled runtime: Kron4ek's vanilla WoW64 build of the Wine 11.0 stable release. It needs
# only glibc 2.25 and runs on the host's own loader and libraries, so it goes in after
# quick-sharun and stays untouched by it.
readonly WINE_VERSION="11.0"
readonly WINE_NAME="wine-${WINE_VERSION}-amd64-wow64"
readonly WINE_URL="https://github.com/Kron4ek/Wine-Builds/releases/download/${WINE_VERSION}/${WINE_NAME}.tar.xz"
readonly WINE_SHA256="39574efa1132c3ca0d5c77dd2eddbe4a49cca0d6cc2c290ff4924493a1c40314"
# Build-time tools and files no player needs.
readonly WINE_DEV_BINS=(function_grep.pl widl winebuild winecpp winedump wineg++ winegcc
                        winemaker wmc wrc)

PYTHON="${PYTHON:-python3}"
BUILD_ROOT="$PROJECT_DIR/build/appimage"
TOOLS_CACHE="${TOOLS_CACHE:-$PROJECT_DIR/build/tools}"
DIST_DIR="$PROJECT_DIR/dist"
SQFS_COMP_LEVEL="${SQFS_COMP_LEVEL:-15}"
CHILD_PIDS=()

log_info()  { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
log_ok()    { printf '\033[0;32m[ OK ]\033[0m %s\n' "$*"; }
log_error() { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; }
die()       { log_error "$*"; exit 1; }

usage() {
    sed -n '6,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-2}"
}

stop_children() {
    local pid
    for pid in "${CHILD_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
}
trap stop_children EXIT
trap 'exit 130' INT TERM

require_tools() {
    local missing=() tool
    for tool in "$@"; do
        command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
    done
    ((${#missing[@]} == 0)) || die "missing tools: ${missing[*]}"
}

sha256_matches() {
    [[ "$(sha256sum "$1" | cut -d' ' -f1)" == "$2" ]]
}

# The cache name carries the hash, so a new pin never meets an old file. Downloads keep the
# server's modification time (curl -R).
fetch_pinned() {
    local name="$1" url="$2" sha="$3" dest part
    dest="$TOOLS_CACHE/$name-${sha:0:12}"
    if [[ -f "$dest" ]] && sha256_matches "$dest" "$sha"; then
        FETCHED="$dest"
        return
    fi
    rm -f "$dest"
    mkdir -p "$TOOLS_CACHE"
    part="$(mktemp "$dest.part.XXXXXX")"
    log_info "downloading $url"
    if ! curl -fsSLR --retry 3 -o "$part" "$url"; then
        rm -f "$part"
        die "download failed: $url"
    fi
    if ! sha256_matches "$part" "$sha"; then
        rm -f "$part"
        die "sha256 mismatch for $url, expected $sha"
    fi
    cp -a "$part" "$dest"
    rm -f "$part"
    FETCHED="$dest"
}

ensure_tools() {
    fetch_pinned quick-sharun "$QUICK_SHARUN_URL" "$QUICK_SHARUN_SHA256"
    QUICK_SHARUN="$FETCHED"
    fetch_pinned uruntime-squashfs "$URUNTIME_URL" "$URUNTIME_SHA256"
    URUNTIME="$FETCHED"
    fetch_pinned appimagetool "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256"
    APPIMAGETOOL="$FETCHED"
    chmod +x "$QUICK_SHARUN" "$URUNTIME" "$APPIMAGETOOL"
    if [[ -n "${WINE_TARBALL:-}" ]]; then
        [[ -f "$WINE_TARBALL" ]] || die "WINE_TARBALL not found: $WINE_TARBALL"
        sha256_matches "$WINE_TARBALL" "$WINE_SHA256" \
            || die "sha256 mismatch for $WINE_TARBALL, expected $WINE_SHA256"
    else
        fetch_pinned "$WINE_NAME.tar.xz" "$WINE_URL" "$WINE_SHA256"
        WINE_TARBALL="$FETCHED"
    fi
}

read_versions() {
    VERSION="$("$PYTHON" -I -c '
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    print(tomllib.load(f)["project"]["version"])' "$PROJECT_DIR/pyproject.toml")"
    [[ -n "$VERSION" ]] || die "no version in pyproject.toml"
    local code_version modified
    code_version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$PROJECT_DIR/$PACKAGE/__init__.py")"
    [[ "$code_version" == "$VERSION" ]] \
        || die "pyproject.toml says $VERSION, $PACKAGE/__init__.py says $code_version"
    modified="$(git -C "$PROJECT_DIR" status --porcelain)" || die "not a git checkout: $PROJECT_DIR"
    if [[ "${RELEASE:-0}" == 1 ]]; then
        [[ -z "$modified" ]] || die "a release is built from an unmodified tree"
        GITSTAMP=""
    elif [[ -n "${HOST_GITSTAMP:-}" ]]; then
        # The arch target's host decides the name, so it gates the file this run built.
        GITSTAMP="$HOST_GITSTAMP"
    else
        GITSTAMP="$(git -C "$PROJECT_DIR" rev-parse --short=7 HEAD)" || die "no commit to stamp"
        [[ -z "$modified" ]] || GITSTAMP="$GITSTAMP-dirty"
    fi
    APPIMAGE_FILE="$ARTIFACT_NAME-$VERSION${GITSTAMP:+-$GITSTAMP}-x64-sharun.AppImage"
}

# setuptools builds inside the folder it is given; a fresh copy keeps files deleted from the
# source out of the image.
copy_source() {
    SOURCE_COPY="$BUILD_ROOT/source"
    mkdir -p "$SOURCE_COPY"
    tar -C "$PROJECT_DIR" --exclude=./build --exclude=./dist --exclude=./.venv --exclude=./.git \
        --exclude='*.egg-info' --exclude=__pycache__ --exclude=.pytest_cache \
        --exclude=.ruff_cache -cf - . | tar -C "$SOURCE_COPY" -xf -
}

make_venv() {
    VENV="$BUILD_ROOT/venv"
    log_info "build venv with $("$PYTHON" -V)"
    "$PYTHON" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    # The versions the test suite ran against, not whatever is newest today.
    "$VENV/bin/python" -m pip install --quiet --constraint "$SCRIPT_DIR/appimage-constraints.txt" \
        "$SOURCE_COPY"
    PY_VER="$("$VENV/bin/python" -c 'import sys; print(f"python{sys.version_info[0]}.{sys.version_info[1]}")')"
    SITE_PACKAGES="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
    QT_DIR="$SITE_PACKAGES/PySide6/Qt"
    [[ -d "$QT_DIR/lib" ]] || die "PySide6 brought no Qt: $QT_DIR"
}

write_entry_files() {
    ENTRY="$BUILD_ROOT/$PACKAGE-entry"
    cat > "$ENTRY" <<EOF
#!/bin/sh
exec python3 -m $PACKAGE "\$@"
EOF
    chmod +x "$ENTRY"

    APP_ID="$("$VENV/bin/python" -I -c "from $PACKAGE import APP_ID; print(APP_ID)")"
    DESKTOP_FILE="$BUILD_ROOT/$APP_ID.desktop"
    # The same entry the launcher installs for GNOME, with the AppImage's own entry point.
    "$VENV/bin/python" -I -c "
import sys
from pathlib import Path
from $PACKAGE.desktop import desktop_entry
text = desktop_entry(Path('/$PACKAGE-entry')).replace('Exec=/$PACKAGE-entry', 'Exec=$PACKAGE-entry')
Path(sys.argv[1]).write_text(text, encoding='utf-8')" "$DESKTOP_FILE"
    grep -q "^Exec=$PACKAGE-entry\$" "$DESKTOP_FILE" || die "desktop entry has no Exec line for the entry"
    ICON_FILE="$SOURCE_COPY/$PACKAGE/data/icons/hicolor/256x256/apps/$APP_ID.png"
    [[ -f "$ICON_FILE" ]] || die "no 256 px icon: $ICON_FILE"
}

run_quick_sharun() {
    local args=("$ENTRY") lib dir plugin unresolved
    for lib in Core Gui Widgets Network Svg DBus XcbQpa WaylandClient OpenGL; do
        [[ -f "$QT_DIR/lib/libQt6$lib.so.6" ]] || die "PySide6 has no libQt6$lib.so.6"
        args+=("$QT_DIR/lib/libQt6$lib.so.6")
    done
    # Plugins go in for dependency tracing only; Qt loads PySide6's own copies through qt.conf.
    for dir in platforms platformthemes platforminputcontexts xcbglintegrations \
            wayland-decoration-client wayland-graphics-integration-client \
            wayland-shell-integration iconengines generic networkinformation tls; do
        for plugin in "$QT_DIR/plugins/$dir"/*.so; do
            [[ -f "$plugin" && "${plugin##*/}" != libqgtk3.so ]] && args+=("$plugin")
        done
    done
    for plugin in "$QT_DIR"/plugins/imageformats/lib{qjpeg,qsvg,qico,qgif,qwebp}.so; do
        [[ -f "$plugin" ]] || continue
        unresolved="$(ldd "$plugin" | awk '/not found/ {print $1}' | tr '\n' ' ')"
        [[ -z "$unresolved" ]] || die "$(basename "$plugin") cannot load on this host, missing: $unresolved"
        args+=("$plugin")
    done

    log_info "quick-sharun (log: $BUILD_ROOT/quick-sharun.log)"
    (
        cd "$BUILD_ROOT"
        export APPDIR TMPDIR="$BUILD_ROOT/tmp" PATH="$VENV/bin:$PATH"
        export ICON="$ICON_FILE" DESKTOP="$DESKTOP_FILE" MAIN_BIN="${ENTRY##*/}"
        export DEPLOY_PYTHON=1 DEPLOY_QT=0 DEPLOY_COMMON_LIBS=1
        export DEPLOY_GTK=0 DEPLOY_GDK=0 DEPLOY_GLYCIN=0
        # The launcher draws with Qt's raster engine; GPU drivers stay the host's.
        export USE_HOST_DRIVERS=1 DEPLOY_OPENGL=0 DEPLOY_VULKAN=0
        export SKIP_INTEGRITY_CHECKS=0
        "$QUICK_SHARUN" "${args[@]}"
    ) > "$BUILD_ROOT/quick-sharun.log" 2>&1 || {
        tail -30 "$BUILD_ROOT/quick-sharun.log" >&2
        die "quick-sharun failed"
    }
}

add_python_tree() {
    APPDIR_SP="$APPDIR/shared/lib/$PY_VER/site-packages"
    # DEPLOY_PYTHON brings the build host's own Python packages along; the image gets only ours.
    rm -rf "$APPDIR_SP"
    mkdir -p "$APPDIR_SP"
    cp -a "$SITE_PACKAGES"/. "$APPDIR_SP/"
    [[ -d "$APPDIR_SP/$PACKAGE" ]] || die "the launcher package did not land in the image"

    cat >> "$APPDIR/.env" <<EOF
PYTHONPATH=\${SHARUN_DIR}/shared/lib/$PY_VER/site-packages
PYTHONNOUSERSITE=1
EOF
    # Qt finds PySide6's plugins and translations only through this file (sharun 2025-07+).
    cat > "$APPDIR/bin/qt.conf" <<EOF
[Paths]
Prefix = ../shared/lib/$PY_VER/site-packages/PySide6/Qt
Plugins = plugins
Translations = translations
EOF
}

debloat() {
    # System Qt that ldd tracing pulled in would clash with PySide6's own build.
    rm -f "$APPDIR"/shared/lib/libQt6*.so* "$APPDIR"/shared/lib/libQt5*.so*
    rm -rf "$APPDIR"/shared/lib/qt6 "$APPDIR"/shared/lib/qt5
    find "$APPDIR" -type d -name __pycache__ -prune -exec rm -rf {} +
    find "$APPDIR" -name '*.pyc' -delete
    rm -rf "$APPDIR_SP"/pip "$APPDIR_SP"/pip-* "$APPDIR_SP"/setuptools "$APPDIR_SP"/setuptools-* \
           "$APPDIR_SP"/_distutils_hack "$APPDIR_SP"/pkg_resources
    local pyside="$APPDIR_SP/PySide6"
    rm -rf "$pyside"/Qt/qml "$pyside"/Qt/libexec "$pyside"/Qt/metatypes \
           "$pyside"/Qt/lib/libQt6WebEngine* "$pyside"/Qt/lib/libQt6Quick* \
           "$pyside"/Qt/lib/libQt6Qml* "$pyside"/Qt/lib/libQt6Designer* \
           "$pyside"/Qt/lib/libQt6Multimedia* "$pyside"/Qt/lib/libQt6Pdf* \
           "$pyside"/Qt/lib/libQt63D* "$pyside"/Qt/lib/libQt6Bluetooth* \
           "$pyside"/Qt/lib/libQt6Nfc* "$pyside"/Qt/lib/libQt6Sensors* \
           "$pyside"/Qt/lib/libQt6SerialPort* "$pyside"/Qt/lib/libQt6Test* \
           "$pyside"/Qt/lib/libQt6WebSockets* "$pyside"/Qt/lib/libQt6Charts* \
           "$pyside"/Qt/lib/libQt6DataVisualization* "$pyside"/Qt/lib/libQt6Graphs* \
           "$pyside"/Qt/lib/libQt6Location* "$pyside"/Qt/lib/libQt6SpatialAudio* \
           "$pyside"/Qt/lib/libQt6TextToSpeech* "$pyside"/Qt/lib/libQt6RemoteObjects* \
           "$pyside"/Qt/lib/libQt6Scxml* "$pyside"/Qt/lib/libQt6HttpServer* \
           "$pyside"/assistant "$pyside"/designer "$pyside"/linguist "$pyside"/lupdate \
           "$pyside"/lrelease "$pyside"/qmlls "$pyside"/qmlformat "$pyside"/qmllint \
           "$pyside"/include "$pyside"/typesystems "$pyside"/glue "$pyside"/scripts
    # The launcher draws its own theme. Qt's GTK theme would load the host's GTK into a
    # process that runs the image's glibc.
    rm -f "$pyside/Qt/plugins/platformthemes/libqgtk3.so"
    # Python's readline, curses and dbm modules: nothing in the launcher imports them.
    rm -f "$APPDIR"/shared/lib/lib{readline,gdbm,gdbm_compat,ncursesw,panelw}.so* \
          "$APPDIR"/shared/lib/"$PY_VER"/lib-dynload/{readline,_curses,_curses_panel,_dbm,_gdbm}.*.so
    # The launcher speaks English; Qt's own English strings need no file.
    if [[ -d "$pyside/Qt/translations" ]]; then
        find "$pyside/Qt/translations" -type f -delete
    fi
}

# sharun's loader does not search RUNPATH (libQt6Gui would take the host's libQt6DBus), so
# lib.path points at site-packages instead of quick-sharun's copy of the venv.
prune_tracing_copies() {
    local copy="$APPDIR/lib$VENV" venv_sp="+$VENV/lib/$PY_VER/site-packages" dir line kept=()
    rm -rf "$copy"
    dir="${copy%/*}"
    while [[ "$dir" != "$APPDIR/lib" ]] && rmdir "$dir" 2>/dev/null; do
        dir="${dir%/*}"
    done
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == "$venv_sp"* ]]; then
            line="+/$PY_VER/site-packages${line#"$venv_sp"}"
        fi
        if [[ "$line" == +* && "$line" != "+" && ! -d "$APPDIR/lib${line#+}" ]]; then
            continue
        fi
        kept+=("$line")
    done < "$APPDIR/lib/lib.path"
    printf '%s\n' "${kept[@]}" > "$APPDIR/lib/lib.path"
}

add_license_files() {
    local file
    for file in "${LICENSE_FILES[@]}"; do
        cp -a "$SOURCE_COPY/$file" "$APPDIR/$file"
    done
}

# THIRD_PARTY_LICENSES.txt points here for the packages behind the bundled libraries.
record_system_libraries() {
    local list="$APPDIR/SYSTEM-LIBRARIES.txt" file name owner
    if ! command -v pacman >/dev/null 2>&1; then
        printf 'Not recorded: this image was not built on Arch Linux.\n' > "$list"
        return
    fi
    {
        printf 'The libraries in shared/lib and the Arch Linux packages they were taken from.\n\n'
        for file in "$APPDIR"/shared/lib/*.so*; do
            [[ -f "$file" && ! -L "$file" ]] || continue
            name="${file##*/}"
            if owner="$(pacman -Qo "/usr/lib/$name" 2>/dev/null)"; then
                printf '%s: %s\n' "$name" "${owner##* is owned by }"
            else
                printf '%s: part of sharun\n' "$name"
            fi
        done
    } > "$list"
}

add_wine() {
    local wine_dir="$APPDIR/opt/wine" bin
    log_info "bundled runtime: $WINE_NAME"
    mkdir -p "$APPDIR/opt"
    # As root in the container, tar would keep the tarball's owners, which the host user
    # cannot delete afterwards.
    tar --no-same-owner --transform "s|^$WINE_NAME|wine|" -xpf "$WINE_TARBALL" -C "$APPDIR/opt"
    [[ -x "$wine_dir/bin/wine" ]] || die "no bin/wine in $WINE_TARBALL"
    rm -rf "$wine_dir/include" "$wine_dir/share/man" "$wine_dir/share/applications"
    for bin in "${WINE_DEV_BINS[@]}"; do
        rm -f "$wine_dir/bin/$bin"
    done
    find "$wine_dir/lib" -name '*.a' -delete
}

fix_icons() {
    # KDE's thumbnailer cannot follow symlink chains inside the squashfs.
    local file resolved
    for file in "$APPDIR/.DirIcon" "$APPDIR"/*.png "$APPDIR"/*.svg; do
        [[ -L "$file" ]] || continue
        resolved="$(readlink -f "$file")"
        [[ -f "$resolved" ]] || die "dangling icon link: $file"
        rm "$file"
        cp -a "$resolved" "$file"
    done
    [[ -f "$APPDIR/$APP_ID.png" ]] || cp -a "$ICON_FILE" "$APPDIR/$APP_ID.png"
}

pin_host_cache() {
    # The AppRun otherwise moves XDG_CACHE_HOME to its own folder; the launcher keeps its data
    # in the player's real XDG folders.
    grep -q "USE_HOST_XDG_CACHE_HOME" "$APPDIR/AppRun.lib" 2>/dev/null \
        || die "AppRun.lib has no USE_HOST_XDG_CACHE_HOME switch any more: quick-sharun changed"
    grep -q "^MAIN_BIN=" "$APPDIR/AppRun.sh" || die "AppRun.sh has no MAIN_BIN line: quick-sharun changed"
    sed -i '0,/^MAIN_BIN=/s//export USE_HOST_XDG_CACHE_HOME=1\n&/' "$APPDIR/AppRun.sh"
    grep -q "^export USE_HOST_XDG_CACHE_HOME=1$" "$APPDIR/AppRun.sh" || die "could not pin the XDG cache"
}

package_appimage() {
    mkdir -p "$DIST_DIR"
    OUTPUT="$DIST_DIR/$APPIMAGE_FILE"
    rm -f "$OUTPUT"
    log_info "packing $APPIMAGE_FILE (squashfs, zstd $SQFS_COMP_LEVEL)"
    # appimagetool is an AppImage itself; extracting it needs no FUSE (containers have none).
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" --no-appstream --runtime-file "$URUNTIME" \
        --comp zstd --mksquashfs-opt -Xcompression-level --mksquashfs-opt "$SQFS_COMP_LEVEL" \
        "$APPDIR" "$OUTPUT" > "$BUILD_ROOT/appimagetool.log" 2>&1 || {
        tail -20 "$BUILD_ROOT/appimagetool.log" >&2
        die "appimagetool failed"
    }
}

write_provenance() {
    local glibc gcc_version
    glibc="$(getconf GNU_LIBC_VERSION)"
    gcc_version="$(cc --version | head -1)"
    {
        printf 'artifact: %s\n' "$APPIMAGE_FILE"
        printf 'version: %s%s\n' "$VERSION" "${GITSTAMP:+ ($GITSTAMP)}"
        printf 'build date: %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        printf 'build host: %s\n' "$(sed -n 's/^PRETTY_NAME="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' /etc/os-release)"
        printf 'glibc: %s\n' "$glibc"
        printf 'compiler: %s\n' "$gcc_version"
        printf 'python: %s\n' "$("$VENV/bin/python" -V)"
        printf 'pyside6: %s\n' "$("$VENV/bin/python" -c 'import PySide6; print(PySide6.__version__)')"
        printf 'quick-sharun: %s\n' "$QUICK_SHARUN_COMMIT"
        printf 'uruntime: %s\n' "$URUNTIME_URL"
        printf 'appimagetool: %s\n' "$APPIMAGETOOL_URL"
        printf 'wine: %s (sha256 %s)\n' "$WINE_NAME" "$WINE_SHA256"
    } > "$DIST_DIR/build-info.txt"
    (cd "$DIST_DIR" && sha256sum -- "$APPIMAGE_FILE" > SHA256SUMS)
}

gate_appdir() {
    local found
    [[ ! -e "$APPDIR/bin/01-path-mapping-hardcoded.hook" ]] \
        || die "gate: quick-sharun patched hardcoded /usr paths to /tmp (01-path-mapping-hardcoded.hook)"
    found="$(find "$APPDIR/bin" -name '*.hook' -exec grep -l '/tmp/' {} + || [[ $? == 1 ]])"
    [[ -z "$found" ]] || die "gate: hooks that use /tmp: $found"
    found="$(find "$APPDIR/shared/lib" "$APPDIR/lib" \( -name 'libgallium*' -o -name '*_dri.so' \
        -o -name 'libvulkan_*.so' -o -name 'libEGL_mesa*' -o -name 'libGLX_mesa*' \) -print -quit 2>/dev/null)"
    [[ -z "$found" ]] || die "gate: Mesa landed in the image: $found"
    [[ -f "$APPDIR_SP/PySide6/Qt/plugins/platforms/libqxcb.so" ]] || die "gate: no xcb platform plugin"
    ! grep -q -e "$BUILD_ROOT" -e "/venv/" "$APPDIR/lib/lib.path" \
        || die "gate: lib.path still names the build venv"
    [[ ! -e "$APPDIR/lib$VENV" ]] || die "gate: quick-sharun's copy of the venv is still in the image"
    for found in "${LICENSE_FILES[@]}" SYSTEM-LIBRARIES.txt; do
        [[ -s "$APPDIR/$found" ]] || die "gate: $found missing at the top of the image"
    done
    [[ -x "$APPDIR/opt/wine/bin/wine" && -x "$APPDIR/opt/wine/bin/wineserver" ]] \
        || die "gate: the bundled Wine is incomplete"
    found="$(readelf -l "$APPDIR/opt/wine/bin/wine")"
    [[ "$found" == *"interpreter: /lib64/ld-linux-x86-64.so.2"* ]] \
        || die "gate: the bundled wine's interpreter was changed"
    log_ok "gate: no /tmp hooks, no Mesa, Qt plugins present, Wine untouched"
}

# Each check starts the AppImage the way a player would. A failed gate leaves its folder in
# build/ to look at; the next build clears it.
gate_appimage() {
    local image="$1" out work
    [[ -x "$image" ]] || die "not an executable file: $image"
    mkdir -p "$BUILD_ROOT"
    work="$(mktemp -d "$BUILD_ROOT/gate.XXXXXX")"

    out="$(env -u DISPLAY -u WAYLAND_DISPLAY HOME="$work" XDG_CONFIG_HOME="$work/config" \
        XDG_DATA_HOME="$work/data" XDG_CACHE_HOME="$work/cache" XDG_STATE_HOME="$work/state" \
        "$image" --version 2>&1)" || die "gate: --version failed without a display: $out"
    [[ "$out" == *" $VERSION ("* ]] || die "gate: --version printed '$out'"
    log_ok "gate: --version without a display: $out"

    (cd "$work" && "$image" --appimage-extract >/dev/null 2>&1) || die "gate: extraction failed"
    out="$(env -u DISPLAY QT_QPA_PLATFORM=offscreen "$work/squashfs-root/bin/python3" -c '
import ssl, sys
from PySide6.QtWidgets import QApplication
from PySide6.QtDBus import QDBusConnection
app = QApplication(sys.argv)
print(app.platformName(), ssl.OPENSSL_VERSION)' 2>&1)" || die "gate: Qt or ssl failed inside the image: $out"
    [[ "$out" == offscreen\ OpenSSL* ]] || die "gate: Qt/ssl check printed '$out'"
    log_ok "gate: Qt initialises, QtDBus and ssl load: $out"

    out="$(env -i HOME="$work" PATH=/usr/bin:/bin "$work/squashfs-root/opt/wine/bin/wine" --version 2>&1)" \
        || die "gate: the bundled wine does not start on the host: $out"
    [[ "$out" == "wine-$WINE_VERSION" ]] || die "gate: bundled wine says '$out'"
    log_ok "gate: bundled $out starts with the host's loader"

    gate_wm_class "$image" "$work"
    rm -rf "$work"
}

# StartupWMClass must be what Qt really sets, or docks show a generic icon.
gate_wm_class() {
    local image="$1" work="$2" display xvfb_pid app_pid wid="" wm_class="" expected i
    expected="$(sed -n 's/^StartupWMClass=//p' "$work/squashfs-root"/*.desktop)"
    [[ -n "$expected" ]] || die "gate: the desktop entry has no StartupWMClass"

    # Xvfb picks a free display and writes its number once it accepts clients.
    Xvfb -displayfd 3 -screen 0 1280x1024x24 -nolisten tcp 3>"$work/display" >/dev/null 2>&1 &
    xvfb_pid=$!
    CHILD_PIDS+=("$xvfb_pid")
    for ((i = 0; i < 100; i++)); do
        [[ -s "$work/display" ]] && break
        kill -0 "$xvfb_pid" 2>/dev/null || die "gate: Xvfb did not start"
        sleep 0.1
    done
    [[ -s "$work/display" ]] || die "gate: Xvfb reported no display"
    display=":$(tr -dc '0-9' < "$work/display")"

    env -u WAYLAND_DISPLAY DISPLAY="$display" HOME="$work" XDG_CONFIG_HOME="$work/config" \
        XDG_DATA_HOME="$work/data" XDG_CACHE_HOME="$work/cache" XDG_STATE_HOME="$work/state" \
        "$image" >"$work/window.log" 2>&1 &
    app_pid=$!
    CHILD_PIDS+=("$app_pid")
    # A bare Xvfb has no window manager, so the window is found by its title.
    for ((i = 0; i < 300; i++)); do
        [[ -z "$wid" ]] || break
        kill -0 "$app_pid" 2>/dev/null || break
        sleep 0.1
        wid="$(DISPLAY="$display" xwininfo -root -tree | awk '/Project Reforged/ && !n {print $1; n = 1}')" \
            || { tail -20 "$work/window.log" >&2; die "gate: xwininfo failed on $display"; }
    done
    if [[ -n "$wid" ]]; then
        wm_class="$(DISPLAY="$display" xprop -id "$wid" WM_CLASS)" \
            || die "gate: xprop could not read the window's WM_CLASS"
    fi
    kill "$app_pid" "$xvfb_pid" 2>/dev/null || true
    wait "$app_pid" "$xvfb_pid" 2>/dev/null || true
    CHILD_PIDS=()
    [[ -n "$wid" ]] || { tail -20 "$work/window.log" >&2; die "gate: no launcher window appeared"; }
    [[ "$wm_class" == *"\"$expected\""* ]] \
        || die "gate: WM_CLASS is ${wm_class:-unset}, the desktop entry says StartupWMClass=$expected"
    log_ok "gate: $wm_class matches StartupWMClass=$expected"
}

build_appimage() {
    require_tools "$PYTHON" curl sha256sum tar patchelf strings ldd readelf cc git
    [[ "${SKIP_RUN_GATES:-0}" == 1 ]] || require_tools "${GATE_TOOLS[@]}"
    read_versions
    log_info "$ARTIFACT_NAME $VERSION${GITSTAMP:+ ($GITSTAMP)}"
    ensure_tools

    # quick-sharun only ever adds to an AppDir; every build starts from nothing.
    rm -rf "$BUILD_ROOT"
    mkdir -p "$BUILD_ROOT/tmp"
    APPDIR="$BUILD_ROOT/AppDir"

    copy_source
    make_venv
    write_entry_files
    run_quick_sharun
    add_python_tree
    debloat
    prune_tracing_copies
    add_license_files
    record_system_libraries
    add_wine
    fix_icons
    pin_host_cache
    gate_appdir
    package_appimage
    write_provenance
    if [[ "${SKIP_RUN_GATES:-0}" == 1 ]]; then
        log_info "run gates skipped here (SKIP_RUN_GATES=1)"
    else
        gate_appimage "$OUTPUT"
    fi
    log_ok "built $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
}

# The image ships Arch's Python, not the one the development venv runs; the suite runs on it.
run_suite() {
    local venv="$BUILD_ROOT/test-venv" source="$BUILD_ROOT/source"
    # Root writes through the read-only folders the permission tests set up.
    ((EUID != 0)) || die "the test suite cannot run as root"
    [[ -d "$source" ]] || die "no source copy in $BUILD_ROOT: run the appimage target first"
    log_info "test suite on $("$PYTHON" -V)"
    "$PYTHON" -m venv "$venv"
    "$venv/bin/python" -m pip install --quiet --upgrade pip
    "$venv/bin/python" -m pip install --quiet --constraint "$SCRIPT_DIR/appimage-constraints.txt" \
        "pytest==$PYTEST_VERSION" "$source"
    (cd "$source" && QT_QPA_PLATFORM=offscreen "$venv/bin/python" -m pytest -q -p no:cacheprovider) \
        > "$BUILD_ROOT/suite.log" 2>&1 || {
        tail -30 "$BUILD_ROOT/suite.log" >&2
        die "the test suite failed on $("$PYTHON" -V)"
    }
    log_ok "suite on $("$PYTHON" -V): $(tail -1 "$BUILD_ROOT/suite.log")"
}

# The container sees the project at /src; a WINE_TARBALL outside it is mounted beside it.
build_in_arch() {
    local mounts=(-v "$PROJECT_DIR:/src:Z") env_args=() image_age
    require_tools podman realpath "${GATE_TOOLS[@]}"
    read_versions
    if ! podman image exists "$BUILD_IMAGE"; then
        log_info "building the Arch build image"
        podman build --pull=always -t "$BUILD_IMAGE" -f "$SCRIPT_DIR/Containerfile.arch" "$SCRIPT_DIR"
    else
        image_age="$(podman image inspect --format '{{.Created}}' "$BUILD_IMAGE")"
        log_info "Arch build image from $image_age (remove it to update: podman rmi $BUILD_IMAGE)"
    fi
    if [[ -n "${WINE_TARBALL:-}" ]]; then
        [[ -f "$WINE_TARBALL" ]] || die "WINE_TARBALL not found: $WINE_TARBALL"
        mounts+=(-v "$(realpath "$WINE_TARBALL"):/wine/$WINE_NAME.tar.xz:ro,Z")
        env_args+=(-e "WINE_TARBALL=/wine/$WINE_NAME.tar.xz")
    fi
    [[ -n "${RELEASE:-}" ]] && env_args+=(-e "RELEASE=$RELEASE")
    [[ -n "${SQFS_COMP_LEVEL:-}" ]] && env_args+=(-e "SQFS_COMP_LEVEL=$SQFS_COMP_LEVEL")
    [[ -n "$GITSTAMP" ]] && env_args+=(-e "HOST_GITSTAMP=$GITSTAMP")
    podman run --rm "${mounts[@]}" "${env_args[@]}" -e SKIP_RUN_GATES=1 -w /src "$BUILD_IMAGE" \
        tools/build.sh appimage
    podman run --rm --userns=keep-id -e HOME=/tmp "${mounts[@]}" "${env_args[@]}" -w /src \
        "$BUILD_IMAGE" tools/build.sh suite
    gate_appimage "$DIST_DIR/$APPIMAGE_FILE"
    log_ok "built and checked $DIST_DIR/$APPIMAGE_FILE"
}

main() {
    local target="${1:-arch}"
    case "$target" in
        arch) build_in_arch ;;
        appimage) build_appimage ;;
        suite)
            require_tools "$PYTHON"
            run_suite
            ;;
        check)
            [[ $# -eq 2 ]] || usage
            require_tools "$PYTHON" realpath "${GATE_TOOLS[@]}"
            read_versions
            gate_appimage "$(realpath "$2")"
            ;;
        -h|--help) usage 0 ;;
        *) log_error "unknown target: $target"; usage ;;
    esac
}

main "$@"
