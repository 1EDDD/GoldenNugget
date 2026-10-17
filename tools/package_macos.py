"""Finalize the Universal2 app, verify compatibility and create ZIP and DMG."""
from pathlib import Path
import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile

from PyInstaller.utils.osx import set_dylib_dependency_paths, sign_binary

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
APP = DIST / 'Nugget.app'


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    # OpenCV can flatten ARM-only SSL/zstd codecs into the bundle root.
    # Python's own universal libraries must serve Python's extensions there.
    frameworks = APP / 'Contents/Frameworks'
    for name in ['libssl.3.dylib', 'libcrypto.3.dylib', 'libzstd.1.dylib']:
        source = Path(sys.base_prefix) / 'lib' / name
        if not source.exists():
            raise RuntimeError(f'Missing universal Python dependency: {source}')
        target = frameworks / name
        if target.is_symlink():
            target.unlink()
        shutil.copy2(source, target)
        set_dylib_dependency_paths(str(target), '@loader_path')
        sign_binary(str(target), None, None)
    # Read application version without importing the application.
    namespace = {}
    exec((ROOT / 'src/version.py').read_text(), namespace)
    plist = APP / 'Contents/Info.plist'
    data = plistlib.loads(plist.read_bytes())
    data.update(CFBundleShortVersionString=namespace['App_Version'],
                CFBundleVersion=namespace['App_Version'], LSMinimumSystemVersion='14.4')
    plist.write_bytes(plistlib.dumps(data))
    run('codesign', '--force', '--sign', '-', APP)
    report = subprocess.check_output([sys.executable, str(ROOT / 'tools/validate_macos.py'),
                                      str(APP)], text=True)
    json.loads(report)  # Validator must return a complete JSON report and exit successfully.
    (DIST / 'macOS-validation.json').write_text(report)
    archive = DIST / 'Nugget-macOS-Universal.zip'
    run('ditto', '-c', '-k', '--keepParent', APP, archive)
    dmg = DIST / 'Nugget-macOS-Universal2.dmg'
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory) / 'staging'
        staging.mkdir()
        run('ditto', APP, staging / 'Nugget.app')
        (staging / 'Applications').symlink_to('/Applications')
        (staging / 'README.txt').write_text(
            'GoldenNugget — macOS 14.4 Sonoma or later.\n'
            'Universal2: Intel and Apple Silicon.\n'
            'Drag Nugget.app into Applications.\n'
            'Ad-hoc signed; not notarized.\n')
        run('hdiutil', 'create', '-ov', '-volname', 'GoldenNugget Universal2',
            '-icon', '/Users/awesomenull/Projects/GoldenNugget/src/qt/dmg_icon.icns',
            '-srcfolder', staging, '-fs', 'HFS+', '-format', 'UDZO', dmg)
        run('hdiutil', 'verify', dmg)
        mounted = Path(directory) / 'mounted'
        mounted.mkdir()
        run('hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mounted, dmg)
        try:
            if not (mounted / 'Nugget.app').is_dir() or (mounted / 'Nugget.app').is_symlink():
                raise RuntimeError('DMG does not contain a real app bundle')
            run('codesign', '--verify', '--deep', '--strict', mounted / 'Nugget.app')
        finally:
            run('hdiutil', 'detach', mounted)
    (DIST / 'SHA256SUMS-macOS.txt').write_text(''.join(
        f'{hashlib.file_digest(p.open("rb"), "sha256").hexdigest()}  {p.name}\n'
        for p in [archive, dmg]))


if __name__ == '__main__':
    main()
