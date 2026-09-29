"""Run on DGX Spark: provision browser-only files inside OpenShell, without apt/system changes."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.sandbox import get_sandbox


def main():
    sandbox = get_sandbox()
    sandbox.ensure()
    install = sandbox._cli('sandbox', 'exec', '-n', sandbox.name, '--timeout', '300', '--', 'sh', '-c',
        'mkdir -p /sandbox/browser-tools && npm install --prefix /sandbox/browser-tools playwright@1.58.2 && '
        'PLAYWRIGHT_BROWSERS_PATH=/sandbox/browser-tools/browsers /sandbox/browser-tools/node_modules/.bin/playwright install chromium --only-shell', timeout=330)
    if install.returncode:
        raise RuntimeError('Playwright installation failed: ' + install.stderr[-1000:])
    probe = sandbox._cli('sandbox', 'exec', '-n', sandbox.name, '--timeout', '20', '--', 'sh', '-c',
        'find /sandbox/browser-tools/browsers -name headless_shell -type f -exec ldd {} \\;', timeout=30)
    needed = re.findall(r'^\s*(\S+) => not found', probe.stdout, re.M)
    cache = subprocess.check_output(['ldconfig', '-p'], text=True)
    libraries = dict(re.findall(r'^\s*(\S+) .* => (\S+)$', cache, re.M))
    # Both the node and base sandbox are Ubuntu 24.04/aarch64. Copy user-space libraries only.
    skip = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2', 'librt.so.1'}
    with tempfile.TemporaryDirectory(prefix='krovin-browser-') as tmp:
        folder = Path(tmp) / 'lib'; folder.mkdir()
        seen = set()
        while needed:
            name = needed.pop()
            if name in seen or name in skip or name.startswith('ld-linux'):
                continue
            seen.add(name)
            source = libraries.get(name)
            if not source:
                raise RuntimeError('Node does not have required library: ' + name)
            shutil.copy2(source, folder / name)
            deps = subprocess.run(['ldd', source], capture_output=True, text=True).stdout
            needed.extend(re.findall(r'^\s*(\S+) => /', deps, re.M))
        result = sandbox._cli('sandbox', 'upload', sandbox.name, str(folder), '/sandbox/browser-tools', timeout=120)
        if result.returncode:
            raise RuntimeError('Browser library upload failed')
        print('browser_libraries', len(seen))
        fonts = Path(tmp) / 'fonts'; fonts.mkdir()
        for pattern in ('**/DejaVuSans.ttf', '**/NotoSansCJK-Regular.ttc'):
            source = next(Path('/usr/share/fonts').glob(pattern), None)
            if source:
                shutil.copy2(source, fonts / source.name)
        (fonts / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
            '<fontconfig><dir>/sandbox/browser-tools/fonts</dir><cachedir>/sandbox/browser-tools/fontcache</cachedir></fontconfig>')
        result = sandbox._cli('sandbox', 'upload', sandbox.name, str(fonts), '/sandbox/browser-tools', timeout=120)
        if result.returncode:
            raise RuntimeError('Browser font upload failed')
    print('browser_runtime_ready')


if __name__ == '__main__':
    main()
