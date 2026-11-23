# Maintainer: grigio <grigio@users.noreply.github.com>
# Build recipe adapted from the Arch Linux AUR `ladybird` package (Maintainer: Ali Mohammad Pur).
# This package is built by GitHub Actions and attached to a GitHub release. It is NOT published to the AUR.
#
# The following environment variables are supplied by the CI job in scripts/release_bot.py:
#   LADYBIRD_VERSION  - upstream Ladybird tag to build, e.g. 2026.47.7
#   VCPKG_COMMIT      - vcpkg builtin-baseline pinned by that tag's vcpkg.json

pkgname=ladybird
epoch=1
pkgver="${LADYBIRD_VERSION:?LADYBIRD_VERSION must be set by the CI job}"
pkgrel=1
pkgdesc='Truly independent web browser'
# Set by CI (see scripts/release_bot.py): x86_64_v3 or the generic x86_64.
arch=("${PACKAGE_ARCH:?PACKAGE_ARCH must be set by the CI job}")
url='https://github.com/LadybirdBrowser/ladybird'
license=(BSD-2-Clause)
depends=(
  curl
  ffmpeg
  libgl
  libpulse
  qt6-base
  qt6-multimedia
  qt6-positioning
  ttf-liberation
  vulkan-icd-loader
  wayland
  xcb-util-wm
)
makedepends=(
  autoconf-archive
  automake
  cargo
  cmake
  git
  libtool
  make
  nasm
  ninja
  patch
  pkg-config
  python
  qt6-tools
  tar
  unzip
  vulkan-headers
  zip
)
options=('!lto' '!debug' '!buildflags' '!staticlibs' '!emptydirs')
source=(
  "git+${url}#tag=${pkgver}"
  "git+https://github.com/microsoft/vcpkg.git#commit=${VCPKG_COMMIT:?VCPKG_COMMIT must be set by the CI job}"
  'hb-fc-whole-archive.patch'
  'gcc-build.patch'
)
sha256sums=(
  'SKIP'
  'SKIP'
  'e268aed76a27dc8519be00f6c30a59ce2339683127839f8e097d14d92d7b4268'
  '74cc7d68b7531f3fbe0eab9500a79d90f4f5b5ee8e02bcf0d94fbd980a50c2b0'
)

prepare() {
  cd "${srcdir}"

  export VCPKG_ROOT="${srcdir}/vcpkg"
  export VCPKG_DISABLE_METRICS='true'
  export VCPKG_DOWNLOADS="${VCPKG_DOWNLOADS:-${HOME}/.cache/vcpkg/downloads}"
  unset CARGO_TARGET_DIR
  export RUSTUP_TOOLCHAIN="${RUSTUP_TOOLCHAIN:-$(sed -n 's/^channel = "\(.*\)"/\1/p' ladybird/rust-toolchain.toml)}"

  # GCC cannot do LTO on the Release build; match the upstream AUR recipe.
  local use_linker=
  if ! printf '#if defined(__clang__)\nWE ARE ON CLANG\n#endif\n' | "${CC:-/usr/bin/cc}" -E - | grep -q 'WE ARE ON CLANG'; then
    echo 'Disabling LTO on Release build with GCC'
    use_linker='-DENABLE_LTO_FOR_RELEASE=OFF'
  fi

  patch -d ladybird -p1 < hb-fc-whole-archive.patch
  patch -d ladybird -p1 < gcc-build.patch

  "${VCPKG_ROOT}/bootstrap-vcpkg.sh" -disableMetrics

  cmake \
    --preset Release \
    -B build \
    -S ladybird \
    -DBUILD_SHARED_LIBS=OFF \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS="${MARCH_FLAG:?MARCH_FLAG must be set by the CI job}" \
    -DCMAKE_CXX_FLAGS="${MARCH_FLAG:?MARCH_FLAG must be set by the CI job}" \
    -DLADYBIRD_VERSION="${pkgver}" \
    ${use_linker} \
    -DLADYBIRD_VCPKG_TYPE=distribution \
    -DCMAKE_INSTALL_PREFIX='/opt/ladybird' \
    -DCMAKE_TOOLCHAIN_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake" \
    -DENABLE_INSTALL_HEADERS=OFF \
    -DLAGOOM_LINK_POOL_SIZE=2 \
    -GNinja \
    -Wno-dev
}

build() {
  cd "${srcdir}"

  export VCPKG_ROOT="${srcdir}/vcpkg"
  export VCPKG_DISABLE_METRICS='true'
  export VCPKG_DOWNLOADS="${VCPKG_DOWNLOADS:-${HOME}/.cache/vcpkg/downloads}"
  unset CARGO_TARGET_DIR
  export RUSTUP_TOOLCHAIN="${RUSTUP_TOOLCHAIN:-$(sed -n 's/^channel = "\(.*\)"/\1/p' ladybird/rust-toolchain.toml)}"

  cmake --build build
}

package() {
  cd "${srcdir}"

  local _component
  for _component in ladybird_Runtime ladybird_SystemIntegration js wasm; do
    DESTDIR="${pkgdir}" cmake --install build --component "${_component}"
  done

  install -d "${pkgdir}/usr/bin"
  ln -s /opt/ladybird/bin/js "${pkgdir}/usr/bin/js"
  ln -s /opt/ladybird/bin/wasm "${pkgdir}/usr/bin/wasm"

  find "${pkgdir}" -name '*.a' -delete
  find "${pkgdir}" -name '*.cmake' -delete

  install -Dm644 ladybird/LICENSE -t "${pkgdir}/usr/share/licenses/${pkgname}/"
}
