#!/usr/bin/env python3
"""配布の zip の licenses/ にそのまま入れるライセンスの束を作る（係 D，11/15）．読むのは手元の部品だけ（外へは送らない）．

  py -3 -X utf8 make_license_bundle.py --texts <公式の本文を落としたフォルダー> [--out ../package-licenses] --src strata=<道のり> --src node_modules=<道のり> ...（名前は SRC の欄）

--texts には公式の配布元から落とした次の 4 つを置く（このスクリプトは落とさない）:
  node-LICENSE.txt   https://raw.githubusercontent.com/nodejs/node/v<版>/LICENSE（同梱の node.exe と同じ版）
  lgpl-3.0.txt       https://www.gnu.org/licenses/lgpl-3.0.txt
  gpl-3.0.txt        https://www.gnu.org/licenses/gpl-3.0.txt
  mpl-2.0.txt        https://www.mozilla.org/media/MPL/2.0/index.txt
出力に作者の PC の道のりは入れない（部品は名前と版で書く）．部品の版が変わったら流し直す．
"""
import argparse, glob, hashlib, json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 部品の元の置き場は引数 --src 名前=道のり で渡す（作業場の道のりをここに書かない）．
SRC = {
    'strata': None,          # Strata のソースの木（LICENSE などを読む）
    'node_modules': None,    # dsh の node_modules
    'python': None,          # 同梱の Python のフォルダー
    'app_notices': None,     # 枠の THIRD-PARTY-NOTICES.txt
    'cargo_lock': None,      # 枠の Cargo.lock
    'cargo_registry': os.path.join(os.path.expanduser('~'), '.cargo', 'registry', 'src'),
    'font_zen': None,        # OFL-ZenKakuGothicNew.txt
    'qwen': None,            # Qwen Community License 1.0 の LICENSE
    'node_version': '24.19.0',
}
LICFILE = re.compile(r'^(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT)', re.I)
SEP = '\n' + '=' * 78 + '\n'

MIT = """MIT License

Copyright (c) {who}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
ISC = """ISC License

Copyright (c) {who}

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""
BSD3 = """BSD 3-Clause License

Copyright (c) {who}

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""


def rd(p):
    return open(p, encoding='utf-8', errors='replace').read().replace('\r\n', '\n')


def wr(out, rel, text):
    p = os.path.join(out, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8', newline='\r\n').write(text)


def who_of(pj):
    a = pj.get('author')
    if isinstance(a, dict):
        a = a.get('name')
    return a or (pj.get('name') + ' contributors')


def apache_text(nm):
    for p in sorted(glob.glob(os.path.join(nm, '**', 'LICENSE*'), recursive=True))[:4000]:
        try:
            t = rd(p)
        except OSError:
            continue
        if 'Apache License' in t and 'Version 2.0, January 2004' in t and 'END OF TERMS AND CONDITIONS' in t:
            return t
    return None


def npm(out):
    nm = SRC['node_modules']
    sys.path.insert(0, HERE)
    import collect_licenses as CL
    items = CL.node(nm)
    apache = apache_text(nm)
    parts, made = [], []
    for e in sorted(items, key=lambda x: (x['name'], x['version'], x['path'])):
        d = os.path.join(nm, e['path'][len('node_modules/'):])
        texts = [rd(os.path.join(d, f)) for f in e['license_files']]
        note = ''
        if not texts:
            pj = json.load(open(os.path.join(d, 'package.json'), encoding='utf-8-sig'))
            lic = e['license']
            if lic.startswith('MIT'):
                texts = [MIT.format(who=who_of(pj))]
            elif lic == 'ISC':
                texts = [ISC.format(who=who_of(pj))]
            elif lic.startswith('Apache-2.0') and apache:
                texts = [apache]
            elif lic.startswith('MPL-2.0'):
                texts = ['Mozilla Public License 2.0: the full text is in copyleft/MPL-2.0.txt. Source: see copyleft/SOURCES.txt.']
            note = '  (no license file in the package: this notice was made from its package.json)'
            made.append(f"{e['name']}@{e['version']}")
        parts.append(f"{e['name']}@{e['version']}  License: {e['license'] or 'not stated'}{note}\n\n" + '\n\n'.join(t.strip() for t in texts))
    head = (f'Third-party notices for dsh and its npm packages ({len(items)} packages, from its package-lock).\n'
            'Each block is the package name and version, its license, and the license text shipped in the package.\n')
    wr(out, 'npm/THIRD-PARTY-NOTICES-npm.txt', head + SEP + SEP.join(parts) + '\n')
    return len(items), made


def python(out, py=None, folder='python'):
    py = py or SRC['python']
    # Windows の embeddable は直下の LICENSE.txt．Linux の版は lib/python3.x/LICENSE.txt などを探す
    cands = [os.path.join(py, 'LICENSE.txt'), os.path.join(py, 'LICENSE')] + sorted(glob.glob(os.path.join(py, 'lib', 'python3*', 'LICENSE.txt')))
    lic_main = next((p for p in cands if os.path.isfile(p)), None)
    wr(out, f'{folder}/LICENSE-Python.txt', rd(lic_main) if lic_main else '[unchecked] No LICENSE file found in this Python build: add it by hand.\n')
    parts = []
    for di in sorted(glob.glob(os.path.join(py, '**', 'site-packages', '*.dist-info'), recursive=True)):
        name = os.path.basename(di)[:-len('.dist-info')]
        files = []
        for r, ds, fs in os.walk(di):
            for f in sorted(fs):
                if LICFILE.match(f) or os.path.basename(r) == 'licenses' or 'licenses' in os.path.relpath(r, di).split(os.sep):
                    files.append(os.path.join(r, f))
        meta = rd(os.path.join(di, 'METADATA')) if os.path.exists(os.path.join(di, 'METADATA')) else ''
        lic = re.search(r'^License-Expression:\s*(.+)$', meta, re.M) or re.search(r'^License:\s*(.{1,80})$', meta, re.M)
        body = '\n\n'.join(f'--- {os.path.relpath(f, di).replace(os.sep, "/")} ---\n' + rd(f).strip() for f in files) or '(no license file in the package)'
        parts.append(f"{name}  License: {lic.group(1).strip() if lic else 'see below'}\n\n{body}")
    wr(out, f'{folder}/THIRD-PARTY-NOTICES-python.txt',
       f'Python packages bundled with Sync-Strata ({len(parts)}). Python itself: {folder}/LICENSE-Python.txt.\n' + SEP + SEP.join(parts) + '\n')
    return len(parts)


NOTICE_FILE = re.compile(r'(?i)^(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT|AUTHORS)([._-].*)?$|\.license$|^copyright$')


def gather(out, root, folder, title):
    """AppImage の中や ROCm の部品のように，表示のファイルが散らばっている物から全部を集めて 1 つにする．"""
    parts, names, libs = [], [], []
    for r, ds, fs in os.walk(root):
        ds.sort()
        for f in sorted(fs):
            fp = os.path.join(r, f)
            rel = os.path.relpath(fp, root).replace(os.sep, '/')
            if re.search(r'\.(so(\.\d+)*|dll)$', f):
                libs.append(rel)
            if NOTICE_FILE.search(f):
                try:
                    parts.append(f'--- {rel} ---\n' + rd(fp).strip())
                    names.append(rel)
                except OSError:
                    pass
    head = (f'{title}\nNotice files found in the package ({len(names)}), each with its path. Shared libraries in the package ({len(libs)}):\n'
            + '\n'.join('  ' + l for l in libs) + '\n[unchecked] Check that every library above is covered by a notice below.\n')
    wr(out, f'{folder}/THIRD-PARTY-NOTICES.txt', head + SEP + SEP.join(parts) + '\n')
    return len(names), len(libs)


def rust(out):
    os.makedirs(os.path.join(out, 'rust'), exist_ok=True)
    shutil.copyfile(SRC['app_notices'], os.path.join(out, 'rust', 'THIRD-PARTY-NOTICES-app.txt'))
    listed = []
    for l in rd(SRC['app_notices']).splitlines():
        m = re.match(r'^([A-Za-z0-9_.-]+) (\d+\.\d+\.\d+\S*)\s{2,}(.+)$', l)
        if m:
            listed.append(m.groups())
    regs = [os.path.join(SRC['cargo_registry'], d) for d in os.listdir(SRC['cargo_registry'])] if os.path.isdir(SRC['cargo_registry']) else []
    by_text, missing = {}, []
    for name, ver, lic in listed:
        d = next((os.path.join(r, f'{name}-{ver}') for r in regs if os.path.isdir(os.path.join(r, f'{name}-{ver}'))), None)
        fs = [f for f in sorted(os.listdir(d)) if LICFILE.match(f) and os.path.isfile(os.path.join(d, f))] if d else []
        if not fs:
            # 本文が無い部品: Cargo.toml の authors で標準の文を作る（MIT を選べる物は MIT．MPL は copyleft/ の全文）
            authors = ''
            if d and os.path.exists(os.path.join(d, 'Cargo.toml')):
                m2 = re.search(r'^authors\s*=\s*\[([^\]]*)\]', rd(os.path.join(d, 'Cargo.toml')), re.M)
                authors = ', '.join(re.findall(r'"([^"<]+?)\s*(?:<[^>]*>)?"', m2.group(1))) if m2 else ''
            who = authors or f'the {name} authors'
            if re.search(r'\bMIT\b', lic):
                t = MIT.format(who=who)
            elif 'BSD-3-Clause' in lic:
                t = BSD3.format(who=who)
            elif 'MPL-2.0' in lic:
                t = 'Mozilla Public License 2.0: the full text is in copyleft/MPL-2.0.txt. Source: see copyleft/SOURCES.txt.'
            else:
                t = f'{lic}: see https://spdx.org/licenses/'
            missing.append(f'{name} {ver} ({lic})')
            h = hashlib.sha256(t.encode()).hexdigest()
            by_text.setdefault(h, [t, []])[1].append(f'{name} {ver} (no license file in the crate: made from its Cargo.toml)')
            continue
        for f in fs:
            t = rd(os.path.join(d, f)).strip()
            h = hashlib.sha256(t.encode()).hexdigest()
            by_text.setdefault(h, [t, []])[1].append(f'{name} {ver} ({f})')
    parts = [f"Used by: {', '.join(users)}\n\n{t}" for t, users in sorted(by_text.values(), key=lambda x: x[1][0])]
    head = ('Full license texts of the Rust crates in the app (the list with versions: rust/THIRD-PARTY-NOTICES-app.txt).\n'
            'Identical texts are printed once, with the crates that ship them.\n')
    if missing:
        head += 'Crates without a license file in their package (a standard text was made from the license and authors in their Cargo.toml): ' + '; '.join(missing) + '\n'
    wr(out, 'rust/LICENSE-TEXTS-rust.txt', head + SEP + SEP.join(parts) + '\n')
    return len(listed), len(by_text), missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--texts', required=True)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(HERE), 'package-licenses'))
    ap.add_argument('--linux-python', help='Linux 版の Python のフォルダー（あれば python-linux/ を作る）')
    ap.add_argument('--linux-node-version', help='Linux 版の node の版が Windows と違うときだけ（--texts に node-LICENSE-<版>.txt を置く）')
    ap.add_argument('--appimage-dir', help='AppImage を展開したフォルダー（--appimage-extract の squashfs-root．あれば linux-appimage/ を作る．LGPL-2.1 の本文は --texts の lgpl-2.1.txt）')
    ap.add_argument('--rocm-dir', help='HIP 版のエンジンに同梱する ROCm の部品のフォルダー（あれば rocm/ を作る）')
    ap.add_argument('--src', action='append', default=[], metavar='名前=道のり', help='部品の元の置き場（' + '・'.join(k for k in SRC) + '）')
    a = ap.parse_args()
    for kv in a.src:
        k, _, v = kv.partition('=')
        if k not in SRC or not v:
            ap.error(f'--src は 名前=道のり（名前は {", ".join(SRC)}）: {kv}')
        SRC[k] = v
    miss = [k for k, v in SRC.items() if v is None]
    if miss:
        ap.error('--src が足りません: ' + ', '.join(miss))
    out = a.out
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    st = SRC['strata']
    wr(out, 'sync-strata/LICENSE-Strata.txt', rd(os.path.join(st, 'LICENSE')))
    wr(out, 'engine/LICENSE-ggml-llama.cpp.txt', rd(os.path.join(st, 'third_party', 'ggml', 'LICENSE')))
    wr(out, 'engine/LICENSE-project-maya.txt', rd(os.path.join(st, 'third_party', 'project-maya', 'LICENSE')))
    wr(out, 'engine/NOTICE-project-maya.md', rd(os.path.join(st, 'third_party', 'project-maya', 'NOTICE.md')))
    wr(out, 'fonts/OFL-Outfit.txt', rd(os.path.join(st, 'serve', 'web', 'fonts', 'OFL.txt')))
    wr(out, 'fonts/OFL-ZenKakuGothicNew.txt', rd(SRC['font_zen']))
    wr(out, 'nvidia/NOTICE-NVIDIA-cuBLAS.txt', """NVIDIA cuBLAS (cublas64_13.dll, cublasLt64_13.dll, CUDA 13.0)

These files are NVIDIA Corporation's and are redistributed unmodified, as redistributable runtime
components of the NVIDIA CUDA Toolkit, under the NVIDIA CUDA Toolkit End User License Agreement:
https://docs.nvidia.com/cuda/eula/

They are included only so that the Sync-Strata engine (engine/bin/strata.exe) can run, and are
used only by it. Copyright (c) NVIDIA Corporation. All rights reserved. NVIDIA and CUDA are
trademarks of NVIDIA Corporation. The terms of the EULA, including its third-party notices
(Attachment B), apply to these files.
""")
    wr(out, f"node/LICENSE-Node.js-{SRC['node_version']}.txt", rd(os.path.join(a.texts, 'node-LICENSE.txt')))
    wr(out, 'dsh/LICENSE-dsh.txt', rd(os.path.join(SRC['node_modules'], '@deepseek-ai', 'dsh', 'LICENSE')))
    n_npm, made = npm(out)
    n_py = python(out)
    extra = []
    if a.linux_python:
        extra.append(f"python-linux/                          Python (Linux build) and its {python(out, a.linux_python, 'python-linux')} packages")
    if a.linux_node_version:
        wr(out, f'node/LICENSE-Node.js-{a.linux_node_version}.txt', rd(os.path.join(a.texts, f'node-LICENSE-{a.linux_node_version}.txt')))
        extra.append(f'node/LICENSE-Node.js-{a.linux_node_version}.txt  Node.js (Linux build)')
    if a.appimage_dir:
        n, l = gather(out, a.appimage_dir, 'linux-appimage', 'Parts inside the Linux AppImage of the app')
        if os.path.exists(os.path.join(a.texts, 'lgpl-2.1.txt')):
            wr(out, 'copyleft/LGPL-2.1.txt', rd(os.path.join(a.texts, 'lgpl-2.1.txt')))
        extra.append(f'linux-appimage/THIRD-PARTY-NOTICES.txt  Notices found inside the AppImage ({n} files, {l} shared libraries listed)')
    if a.rocm_dir:
        n, l = gather(out, a.rocm_dir, 'rocm', 'AMD ROCm parts shipped with the HIP engine')
        extra.append(f'rocm/THIRD-PARTY-NOTICES.txt           Notices of the AMD ROCm parts ({n} files, {l} libraries listed)')
    n_rust, n_texts, missing = rust(out)
    wr(out, 'copyleft/LGPL-3.0.txt', rd(os.path.join(a.texts, 'lgpl-3.0.txt')))
    wr(out, 'copyleft/GPL-3.0.txt', rd(os.path.join(a.texts, 'gpl-3.0.txt')))
    wr(out, 'copyleft/MPL-2.0.txt', rd(os.path.join(a.texts, 'mpl-2.0.txt')))
    lo = os.path.join(SRC['node_modules'], '@deepseek-ai', 'libreoffice-kit-win32-x64')
    lo_ver = json.load(open(os.path.join(lo, 'package.json'), encoding='utf-8-sig'))['version']
    sh_ver = json.load(open(os.path.join(SRC['node_modules'], '@img', 'sharp-win32-x64', 'package.json'), encoding='utf-8-sig'))['version']
    vips = sorted(os.path.basename(p) for p in glob.glob(os.path.join(SRC['node_modules'], '@img', 'sharp-win32-x64', 'lib', 'libvips-cpp-*.dll')))
    vips_ver = re.sub(r'^libvips-cpp-|\.dll$', '', vips[0]) if vips else '(see the package)'
    wr(out, 'copyleft/SOURCES.txt', f"""Where to get the source code of the bundled parts under LGPL-3.0 and MPL-2.0

All of these are shipped unmodified. Their full license texts are in this folder
(LGPL-3.0.txt with GPL-3.0.txt, which it builds on, and MPL-2.0.txt).

LGPL-3.0-or-later
- libvips {vips_ver} (dsh/node_modules/@img/sharp-win32-x64/lib/*.dll, from the npm package
  @img/sharp-win32-x64 {sh_ver}). Source: https://github.com/libvips/libvips (tag v{vips_ver}) and the build
  scripts at https://github.com/lovell/sharp-libvips . The DLLs are separate files: you may replace them
  with your own build of the same interface.

MPL-2.0
- LibreOffice Kit {lo_ver} (dsh/node_modules/@deepseek-ai/libreoffice-kit and libreoffice-kit-win32-x64).
  The package ships its own source references and patches in libreoffice-kit-win32-x64/sources/
  (core-source.json, core-changes.patch). LibreOffice source: https://github.com/LibreOffice/core
- certifi and tqdm (Python packages, python/Lib/site-packages): https://pypi.org/project/certifi/ ,
  https://pypi.org/project/tqdm/ (source distributions of the same versions).
- Rust crates cssparser, cssparser-macros, selectors, dtoa-short, option-ext (compiled into the app):
  https://crates.io/ (the same versions as listed in rust/THIRD-PARTY-NOTICES-app.txt).
""")
    wr(out, 'models/LICENSE-Qwen-Community-1.0.txt', rd(SRC['qwen']))
    wr(out, 'README.txt', f"""Sync-Strata: licenses of the bundled parts / 同梱する部品のライセンス

Sync-Strata itself is MIT-licensed (sync-strata/LICENSE-Strata.txt; the authors of the fork are added there
[TBD]). The parts below are bundled in this release and keep their own licenses.

Folder / file                          What
sync-strata/LICENSE-Strata.txt         Strata (MIT): the engine, the server and the app are a fork of it
engine/LICENSE-ggml-llama.cpp.txt      llama.cpp / ggml (MIT), compiled into the engine
engine/LICENSE-project-maya.txt        Project Maya (MIT), compiled into the engine
engine/NOTICE-project-maya.md          Project Maya: which files come from it
nvidia/NOTICE-NVIDIA-cuBLAS.txt        NVIDIA cuBLAS DLLs beside the engine (CUDA Toolkit EULA)
node/LICENSE-Node.js-{SRC['node_version']}.txt      Node.js (dsh-node.exe is node.exe {SRC['node_version']}), with the licenses of what Node bundles
dsh/LICENSE-dsh.txt                    dsh by DeepSeek (MIT), the chat app
npm/THIRD-PARTY-NOTICES-npm.txt        All {n_npm} npm packages under dsh, each with its license text
                                       ({len(made)} of them ship no license file; their notice was made from package.json)
python/LICENSE-Python.txt              Python 3.12 (embeddable) and the parts it bundles
python/THIRD-PARTY-NOTICES-python.txt  The {n_py} Python packages, each with its license files
rust/THIRD-PARTY-NOTICES-app.txt       The app (Tauri 2): Strata's license and the list of {n_rust} Rust crates
rust/LICENSE-TEXTS-rust.txt            Full license texts of those crates ({n_texts} distinct texts)
copyleft/LGPL-3.0.txt, GPL-3.0.txt     For libvips (LGPL-3.0-or-later)
copyleft/MPL-2.0.txt                   For LibreOffice Kit, certifi, tqdm and five Rust crates
copyleft/SOURCES.txt                   Where to get the source of the LGPL and MPL parts
fonts/OFL-ZenKakuGothicNew.txt         Zen Kaku Gothic New (SIL OFL 1.1), the chat page's font
fonts/OFL-Outfit.txt                   Outfit (SIL OFL 1.1), the engine's web page font
models/LICENSE-Qwen-Community-1.0.txt  The models (Sync-XS, Sync-S, Sync-M and the shared parts) are derived from
                                       Qwen3.8-Flash-Next and are under this license. They are downloaded
                                       separately from Hugging Face; the license is here for reference.

Not bundled: Microsoft Edge WebView2 Runtime (the app uses the one installed in Windows).
""" + (('\nLinux and HIP builds:\n' + '\n'.join(extra) + '\n') if extra else ''))
    print(f'束を作った: npm {n_npm}（表示を作った {len(made)}: {", ".join(made)}），Python {n_py}，Rust {n_rust}（本文 {n_texts} 種，ファイルなし {len(missing)}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
