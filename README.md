# intrepid-dependencies

Builds the third party libraries that
[intrepid](https://github.com/formalmethods/intrepid) links, the way intrepid
needs them, and publishes them as GitHub releases. intrepid downloads them from
here instead of compiling them itself.

For now this is only [Z3](https://github.com/Z3Prover/z3). intrepid's other
dependencies, googletest and nlohmann/json, are small enough to be fetched as
sources by intrepid's own build.

## What is built

`build_z3.py` downloads the z3 sources pinned in `versions.env`, checks them
against the pinned SHA256, and builds z3 as:

- a **static library** only, which intrepid links into its own libraries, so
  that they need nothing else at run time;
- **position independent**, since it ends up inside `libintrepid.so`;
- with **hidden symbol visibility**, except for z3's own C API;
- in **release** mode, without the z3 executable, examples, tests or language
  bindings; on Windows, against the dynamic MSVC runtime, as intrepid is.

| Platform         | Built on                                   | Package                                  |
| ---------------- | ------------------------------------------ | ---------------------------------------- |
| Linux x86_64     | `manylinux_2_28` container, gcc: glibc 2.28 or newer | `z3-<version>-<rev>-linux-x86_64.tar.gz` |
| Windows x86_64   | `windows-latest`, MSVC                     | `z3-<version>-<rev>-windows-x86_64.zip`  |
| macOS arm64 (Apple silicon) | `macos-15`, Apple clang 16 or later (Xcode 16): macOS 13.3 or newer | `z3-<version>-<rev>-macos-arm64.tar.gz` |

Each package contains:

```
include/              the z3 headers
lib/libz3.a           the library (lib/libz3.lib on Windows)
lib/cmake/z3/         the CMake package, with the z3::libz3 target
LICENSE.txt           the z3 license (MIT)
BUILDINFO.txt         version, compiler and options used
```

so a CMake project uses it with
`find_package(Z3 CONFIG REQUIRED PATHS <package> NO_DEFAULT_PATH)` and links
`z3::libz3`.

## Building locally

You need python 3, CMake 3.25 or newer and Ninja; on Windows, run from a Visual
Studio developer prompt.

```
make            # or: ./build_z3.py
```

The package lands in `dist/`, with a `.sha256` file next to it. The download
and the build tree are kept in `work/`, so running it again only rebuilds what
changed. The compiler is the one CMake picks, or the one named by `CC` and
`CXX`. `make clean` removes both directories.

## Releasing

A release is tagged `z3-<Z3_VERSION>-<Z3_REVISION>`, e.g. `z3-5.0.0-1`.

- **New z3 version:** set `Z3_VERSION` and `Z3_SHA256` in `versions.env` (the
  checksum of `https://github.com/Z3Prover/z3/archive/refs/tags/z3-<version>.tar.gz`)
  and reset `Z3_REVISION` to 1.
- **Same z3, built differently** (flags, compiler, platforms): bump
  `Z3_REVISION`.

Commit and push to `main`, then run:

```
make release
```

It tags the current commit as `z3-<Z3_VERSION>-<Z3_REVISION>` and pushes the
tag. It refuses if the working tree has uncommitted changes, if the current
branch is not `main`, if the commit is not on `origin/main` yet, or if the tag
already exists. The tag starts the workflow in `.github/workflows/z3.yml`, which
builds on every platform, checks that the tag matches `versions.env`, and
publishes the packages and a `SHA256SUMS` file as a release. A newer run of
the workflow on the same branch or pull request cancels the one still going;
a run on a tag, a release, is never cancelled, nor one started by hand.

Then, in intrepid, set `INTREPID_Z3_PACKAGE` to the new `<version>-<rev>` and
the `INTREPID_Z3_SHA256_*` checksums to the ones in `SHA256SUMS`; they are all
in intrepid's `cmake/Z3.cmake`.

## License

The z3 packages are distributed under the z3 license, MIT, included in each of
them as `LICENSE.txt`.
