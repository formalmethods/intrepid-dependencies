#!/usr/bin/env python3
"""
Builds z3 the way intrepid needs it, and packages it.

The z3 version and the checksum of its sources are pinned in versions.env.
The library is built as:

- a static library only: libz3.a, or libz3.lib with MSVC, which intrepid
  links into its own libraries, so that they need nothing else at run time;
- position independent, since it ends up inside libintrepid.so;
- with hidden symbol visibility, except for z3's own C API;
- in release mode, without the z3 executable, examples, tests or bindings.

The result is dist/z3-<version>-<revision>-<platform>.tar.gz (.zip on
Windows), with a .sha256 file next to it. It contains

    include/            the z3 headers
    lib/libz3.a         the library (lib/libz3.lib on Windows)
    lib/cmake/z3/       the CMake package, which defines the z3::libz3 target
    LICENSE.txt         the z3 license
    BUILDINFO.txt       how it was built

Usage:

    build_z3.py                 # download, build and package
    build_z3.py --jobs 8

The compiler is the one CMake picks, or the one named by the CC and CXX
environment variables. CMake 3.25 or newer and Ninja must be on PATH; on
Windows, run from a Visual Studio developer prompt.
"""

import argparse
import datetime
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(HERE, 'work')
DIST_DIR = os.path.join(HERE, 'dist')
SOURCE_URL = 'https://github.com/Z3Prover/z3/archive/refs/tags/z3-{version}.tar.gz'

# Options of z3's own CMakeLists
Z3_CMAKE_OPTIONS = [
    '-DCMAKE_BUILD_TYPE=Release',
    '-DCMAKE_INSTALL_LIBDIR=lib',
    '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
    '-DCMAKE_C_VISIBILITY_PRESET=hidden',
    '-DCMAKE_CXX_VISIBILITY_PRESET=hidden',
    '-DCMAKE_VISIBILITY_INLINES_HIDDEN=ON',
    # intrepid links the dynamic MSVC runtime, as CMake does by default
    '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL',
    '-DZ3_BUILD_LIBZ3_SHARED=OFF',
    '-DZ3_BUILD_EXECUTABLE=OFF',
    '-DZ3_BUILD_TEST_EXECUTABLES=OFF',
    '-DZ3_ENABLE_EXAMPLE_TARGETS=OFF',
    '-DZ3_BUILD_DOCUMENTATION=OFF',
    '-DZ3_BUILD_PYTHON_BINDINGS=OFF',
    '-DZ3_BUILD_JAVA_BINDINGS=OFF',
    '-DZ3_BUILD_DOTNET_BINDINGS=OFF',
    # The sources come from a release archive, without a .git directory,
    # which makes these two abort the configure step
    '-DZ3_INCLUDE_GIT_HASH=OFF',
    '-DZ3_INCLUDE_GIT_DESCRIBE=OFF',
]


def read_versions():
    versions = {}
    with open(os.path.join(HERE, 'versions.env')) as versions_file:
        for line in versions_file:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                versions[key.strip()] = value.strip()
    return versions


def current_platform():
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)
    return '%s-%s' % (system, machine)


def run(command, **kwargs):
    print('+ ' + ' '.join(command), flush=True)
    subprocess.check_call(command, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def fetch_sources(version, expected_sha256):
    """Downloads and checks the z3 sources, returns the extracted directory"""
    os.makedirs(WORK_DIR, exist_ok=True)
    archive = os.path.join(WORK_DIR, 'z3-%s.tar.gz' % version)
    if not os.path.isfile(archive):
        url = SOURCE_URL.format(version=version)
        print('# Downloading ' + url, flush=True)
        with urllib.request.urlopen(url) as response, open(archive + '.part', 'wb') as part:
            shutil.copyfileobj(response, part)
        os.replace(archive + '.part', archive)
    actual = sha256(archive)
    if actual != expected_sha256:
        os.remove(archive)
        sys.exit('Error: %s has SHA256 %s, but versions.env expects %s'
                 % (archive, actual, expected_sha256))
    source_dir = os.path.join(WORK_DIR, 'z3-z3-%s' % version)
    if not os.path.isdir(source_dir):
        with tarfile.open(archive) as sources:
            try:
                sources.extractall(WORK_DIR, filter='data')
            except TypeError:   # python older than 3.9.17, 3.10.12 or 3.11.4
                sources.extractall(WORK_DIR)
    return source_dir


def compiler_description(build_dir):
    compiler = None
    with open(os.path.join(build_dir, 'CMakeCache.txt')) as cache:
        for line in cache:
            if line.startswith('CMAKE_CXX_COMPILER:'):
                compiler = line.split('=', 1)[1].strip()
    if compiler is None:
        return 'unknown'
    if os.path.basename(compiler).lower().startswith('cl'):
        # cl prints its version on stderr, and complains about the missing
        # input file
        result = subprocess.run([compiler], capture_output=True, text=True)
        return result.stderr.splitlines()[0] if result.stderr else compiler
    result = subprocess.run([compiler, '--version'], capture_output=True, text=True)
    return '%s (%s)' % (result.stdout.splitlines()[0], compiler)


def package(stage_dir, name, plat):
    os.makedirs(DIST_DIR, exist_ok=True)
    if plat.startswith('windows'):
        archive = os.path.join(DIST_DIR, name + '.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package_file:
            for root, _, files in os.walk(stage_dir):
                for file_name in sorted(files):
                    path = os.path.join(root, file_name)
                    package_file.write(path, os.path.relpath(path, DIST_DIR))
    else:
        archive = os.path.join(DIST_DIR, name + '.tar.gz')
        with tarfile.open(archive, 'w:gz') as package_file:
            package_file.add(stage_dir, arcname=name)
    with open(archive + '.sha256', 'w') as checksum:
        checksum.write('%s  %s\n' % (sha256(archive), os.path.basename(archive)))
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[1])
    parser.add_argument('--jobs', type=int, help='parallel compile jobs (default: all cores)')
    args = parser.parse_args()

    versions = read_versions()
    version, revision = versions['Z3_VERSION'], versions['Z3_REVISION']
    plat = current_platform()
    if plat not in ('linux-x86_64', 'windows-x86_64'):
        sys.exit('Error: unsupported platform %s' % plat)
    name = 'z3-%s-%s-%s' % (version, revision, plat)

    source_dir = fetch_sources(version, versions['Z3_SHA256'])
    build_dir = os.path.join(WORK_DIR, 'build-' + plat)
    stage_dir = os.path.join(DIST_DIR, name)
    shutil.rmtree(stage_dir, ignore_errors=True)

    run(['cmake', '-S', source_dir, '-B', build_dir, '-G', 'Ninja'] + Z3_CMAKE_OPTIONS)
    build = ['cmake', '--build', build_dir]
    if args.jobs:
        build += ['--parallel', str(args.jobs)]
    run(build)
    run(['cmake', '--install', build_dir, '--prefix', stage_dir])
    # z3.pc hardcodes the staging directory as its prefix, so it would be
    # wrong anywhere else; the CMake package is relocatable
    shutil.rmtree(os.path.join(stage_dir, 'lib', 'pkgconfig'), ignore_errors=True)

    shutil.copyfile(os.path.join(source_dir, 'LICENSE.txt'),
                    os.path.join(stage_dir, 'LICENSE.txt'))
    with open(os.path.join(stage_dir, 'BUILDINFO.txt'), 'w') as info:
        info.write('z3 %s, build revision %s, for %s\n' % (version, revision, plat))
        info.write('sources: %s\n' % SOURCE_URL.format(version=version))
        info.write('sources SHA256: %s\n' % versions['Z3_SHA256'])
        info.write('compiler: %s\n' % compiler_description(build_dir))
        info.write('built: %s\n' % datetime.datetime.now(datetime.timezone.utc)
                   .strftime('%Y-%m-%d %H:%M UTC'))
        info.write('cmake options:\n')
        for option in Z3_CMAKE_OPTIONS:
            info.write('    %s\n' % option)

    archive = package(stage_dir, name, plat)
    print('# Created %s' % os.path.relpath(archive, HERE))


if __name__ == '__main__':
    main()
