"""Merge native dependency wheels into the Intel build environment, fail closed."""
from __future__ import annotations

import importlib.metadata as metadata
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

from packaging.utils import canonicalize_name, parse_wheel_filename

ARCHES = {'x86_64', 'arm64'}
MAGICS = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
          b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
          b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


def arches(path: Path) -> set[str]:
    if path.is_symlink() or not path.is_file():
        return set()
    with path.open('rb') as stream:
        if stream.read(4) not in MAGICS:
            return set()
    return set(subprocess.check_output(['lipo', '-archs', str(path)], text=True).split())


def merge_binary(intel: Path, arm: Path) -> None:
    ia, aa = arches(intel), arches(arm)
    if ARCHES <= ia:
        return
    if 'x86_64' not in ia or 'arm64' not in aa:
        raise RuntimeError(f'Incompatible architecture pair: {intel}: {ia}, {arm}: {aa}')
    with tempfile.TemporaryDirectory() as directory:
        slices = []
        for original, arch, present in [(intel, 'x86_64', ia), (arm, 'arm64', aa)]:
            target = Path(directory) / arch
            if len(present) == 1:
                shutil.copy2(original, target)
            else:
                subprocess.run(['lipo', str(original), '-thin', arch, '-output', str(target)], check=True)
            slices.append(str(target))
        output = Path(directory) / 'universal'
        subprocess.run(['lipo', '-create', *slices, '-output', str(output)], check=True)
        shutil.copymode(intel, output)
        shutil.copy2(output, intel)


def main() -> None:
    if sys.version_info[:2] != (3, 15):
        raise RuntimeError('The macOS build requires Python 3.15')
    if not ARCHES <= arches(Path(sys.base_prefix) / 'Python'):
        raise RuntimeError('Install the universal2 python.org framework, not a thin Python')
    site = Path(sysconfig.get_paths()['purelib'])
    built_wheels = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        # The universal Crypto wheel omits optional Intel-only AVX extensions.
        subprocess.run([sys.executable, '-m', 'pip', 'download', '--no-deps', '--only-binary=:all:',
                        '--platform', 'macosx_14_4_universal2', '--dest', str(work),
                        'pycryptodome==4.0.0'], check=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--force-reinstall',
                        str(next(work.glob('*.whl')))], check=True)
        for dist in list(metadata.distributions()):
            native = [Path(dist.locate_file(p)) for p in dist.files or []
                      if arches(Path(dist.locate_file(p)))]
            if not any(not ARCHES <= arches(p) for p in native):
                continue
            name, version = dist.metadata['Name'], dist.version
            dest = work / canonicalize_name(name)
            dest.mkdir()
            wheel = next((p for p in built_wheels.glob('*.whl')
                          if parse_wheel_filename(p.name)[0] == canonicalize_name(name)
                          and str(parse_wheel_filename(p.name)[1]) == version), None)
            if wheel is None:
                # PySide and shiboken must come from the source builds, never PyPI.
                if canonicalize_name(name) in {'pyside6', 'shiboken6'}:
                    raise RuntimeError(f'Missing source-built ARM wheel: {name}=={version}')
                subprocess.run([sys.executable, '-m', 'pip', 'download', '--no-deps',
                                '--only-binary=:all:', '--platform', 'macosx_14_4_arm64',
                                '--python-version', '3.15', '--implementation', 'cp',
                                '--abi', 'cp315', '--abi', 'abi3', '--abi', 'abi3t',
                                '--dest', str(dest), f'{name}=={version}'], check=True)
                wheel = next(dest.glob('*.whl'))
            unpacked = dest / 'unpacked'
            with zipfile.ZipFile(wheel) as archive:
                archive.extractall(unpacked)
            # Preserve architecture-specific codec libraries under their original names.
            for arm in unpacked.rglob('*'):
                if not arches(arm):
                    continue
                target = site / arm.relative_to(unpacked)
                if target.exists():
                    merge_binary(target, arm)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(arm, target)
            for path in native:
                if path.suffix == '.so' and not ARCHES <= arches(path):
                    raise RuntimeError(f'Extension is still thin: {path}')
            print(f'Universal2: {name}=={version}', flush=True)


if __name__ == '__main__':
    main()
