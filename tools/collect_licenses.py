#!/usr/bin/env python3
"""配布物に入る部品のライセンスを機械的に集める（係 D，11/15）．読むだけ．外へは何も送らない．

  py -3 -X utf8 collect_licenses.py --out <出力フォルダー>
      --node-modules <dsh の node_modules>
      --python <同梱の Python のフォルダー>
      --cargo-lock <枠の Cargo.lock>
      [--cargo-registry <~/.cargo/registry/src>]   （無ければ Cargo の部品は版の一覧だけ）

出力:
  licenses-inventory.json   部品ごとの {kind, name, version, license, license_files, path（集めた元からの相対）}
  licenses-summary.md       ライセンスごとの数と，「確かめが要る」部品（ライセンスが無い・コピーレフト・独自の文）の一覧

出力には集めた元の頭の道のり（ドライブやホーム）を入れない（相対の道のりだけ）．
"""
import argparse, collections, glob, json, os, re, sys

COPYLEFT = re.compile(r'\b(A?GPL|LGPL|MPL|EPL|CDDL|EUPL|OSL|CC-BY-SA|SSPL|BUSL)', re.I)
PERMISSIVE = re.compile(r'^\(?\s*(MIT|ISC|BSD-[23]-Clause|BSD|Apache-2\.0|0BSD|Unlicense|CC0-1\.0|Zlib|BlueOak-1\.0\.0|Python-2\.0|PSF-2\.0|CC-BY-4\.0|Unicode-3\.0|Unicode-DFS-2016|BSL-1\.0)', re.I)
LICFILE = re.compile(r'^(LICEN[CS]E|COPYING|NOTICE|COPYRIGHT|AUTHORS|THIRD[-_]PARTY)', re.I)


def lic_files(d):
    try:
        return sorted(f for f in os.listdir(d) if LICFILE.match(f) and os.path.isfile(os.path.join(d, f)))
    except OSError:
        return []


def norm_license(v):
    if v is None:
        return ''
    if isinstance(v, dict):
        return v.get('type') or ''
    if isinstance(v, list):
        return ' OR '.join(norm_license(x) for x in v)
    return str(v).strip()


def node(root):
    out = []
    pj_paths = glob.glob(os.path.join(root, '*', 'package.json')) + glob.glob(os.path.join(root, '@*', '*', 'package.json'))
    # 入れ子の node_modules も拾う（深い所の版違い）
    for r, ds, fs in os.walk(root):
        if os.path.basename(os.path.dirname(r)) == 'node_modules' or os.path.basename(os.path.dirname(os.path.dirname(r))) == 'node_modules':
            if 'package.json' in fs and r != root:
                pj_paths.append(os.path.join(r, 'package.json'))
    seen = set()
    for pj in sorted(set(os.path.normpath(p) for p in pj_paths)):
        d = os.path.dirname(pj)
        rel = os.path.relpath(d, root).replace(os.sep, '/')
        try:
            j = json.load(open(pj, encoding='utf-8-sig'))
        except Exception:
            continue
        if not j.get('name') or not j.get('version'):
            continue
        key = (j['name'], j['version'], rel)
        if key in seen:
            continue
        seen.add(key)
        lic = norm_license(j.get('license') or j.get('licenses'))
        out.append({'kind': 'npm', 'name': j['name'], 'version': j['version'], 'license': lic,
                    'license_files': lic_files(d), 'path': 'node_modules/' + rel})
    return out


def python(root):
    out = []
    sp = os.path.join(root, 'Lib', 'site-packages')
    for di in sorted(glob.glob(os.path.join(sp, '*.dist-info'))):
        meta = os.path.join(di, 'METADATA')
        name = ver = ''
        lic_expr = lic = ''
        classifiers = []
        if os.path.exists(meta):
            for line in open(meta, encoding='utf-8', errors='replace'):
                if line.strip() == '':
                    break
                k, _, v = line.partition(':')
                v = v.strip()
                if k == 'Name':
                    name = v
                elif k == 'Version':
                    ver = v
                elif k == 'License-Expression':
                    lic_expr = v
                elif k == 'License':
                    lic = v
                elif k == 'Classifier' and v.startswith('License ::'):
                    classifiers.append(v.split('::')[-1].strip())
        files = lic_files(di) + ['licenses/' + f for f in lic_files(os.path.join(di, 'licenses'))]
        if os.path.isdir(os.path.join(di, 'licenses')):
            for r, ds, fs in os.walk(os.path.join(di, 'licenses')):
                for f in fs:
                    p = os.path.relpath(os.path.join(r, f), di).replace(os.sep, '/')
                    if p not in files:
                        files.append(p)
        best = lic_expr or (lic if lic and len(lic) < 80 else '') or ' / '.join(classifiers) or (('(長い文) ' + lic[:60]) if lic else '')
        out.append({'kind': 'python', 'name': name, 'version': ver, 'license': best,
                    'license_files': sorted(set(files)), 'path': os.path.relpath(di, root).replace(os.sep, '/')})
    # Python 本体
    if os.path.exists(os.path.join(root, 'LICENSE.txt')):
        out.append({'kind': 'python', 'name': 'CPython (embeddable)', 'version': '', 'license': 'PSF-2.0（ほかに同梱の部品の表示: LICENSE.txt の中）',
                    'license_files': ['LICENSE.txt'], 'path': '.'})
    return out


def cargo(lock, registry):
    out = []
    txt = open(lock, encoding='utf-8').read()
    pkgs = re.findall(r'\[\[package\]\]\s*\nname = "([^"]+)"\s*\nversion = "([^"]+)"(?:\s*\nsource = "([^"]+)")?', txt)
    regs = []
    if registry and os.path.isdir(registry):
        regs = [os.path.join(registry, d) for d in os.listdir(registry)]
    for name, ver, src in pkgs:
        lic, files = '', []
        if not src:
            lic = '(このリポジトリの物)'
        for rg in regs:
            d = os.path.join(rg, f'{name}-{ver}')
            ct = os.path.join(d, 'Cargo.toml')
            if os.path.exists(ct):
                m = re.search(r'^license\s*=\s*"([^"]*)"', open(ct, encoding='utf-8', errors='replace').read(), re.M)
                if m:
                    lic = m.group(1)
                else:
                    m2 = re.search(r'^license-file\s*=\s*"([^"]*)"', open(ct, encoding='utf-8', errors='replace').read(), re.M)
                    lic = ('(独自の文: ' + m2.group(1) + ')') if m2 else ''
                files = lic_files(d)
                break
        out.append({'kind': 'cargo', 'name': name, 'version': ver, 'license': lic or ('(registry に無い)' if src else lic),
                    'license_files': files, 'path': 'Cargo.lock'})
    return out


def classify(e):
    l = e['license']
    if not l or l.startswith('(registry'):
        return 'ライセンスの記載が無い（中を確かめる）'
    if l.startswith('(このリポジトリ'):
        return ''
    if COPYLEFT.search(l):
        # 「MIT OR Apache-2.0」の類の選べる物は寛容の側を選べる
        if re.search(r'\bOR\b', l, re.I) and PERMISSIVE.search(l.split(' OR ')[0].strip('() ')) or re.search(r'(MIT|Apache-2\.0)\s+OR', l):
            return ''
        return 'コピーレフトの条件あり（ソースの開示・表示の条件を確かめる）'
    if not PERMISSIVE.search(l) and not re.search(r'(MIT|Apache|BSD|ISC|Python|PSF|Unicode|Zlib|0BSD|CC0)', l, re.I):
        return '独自の文か見慣れない名前（本文を読む）'
    if not e['license_files'] and e['kind'] != 'cargo':
        return '表示の文（LICENSE）がファイルに無い（MIT などは表示の同梱が条件．別に足す）'
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--node-modules', required=True)
    ap.add_argument('--python', required=True)
    ap.add_argument('--cargo-lock', required=True)
    ap.add_argument('--cargo-registry', default=os.path.join(os.path.expanduser('~'), '.cargo', 'registry', 'src'))
    a = ap.parse_args()
    inv = []
    if os.path.isdir(a.node_modules):
        inv += node(a.node_modules)
    if os.path.isdir(a.python):
        inv += python(a.python)
    if os.path.exists(a.cargo_lock):
        inv += cargo(a.cargo_lock, a.cargo_registry)
    for e in inv:
        e['check'] = classify(e)
    os.makedirs(a.out, exist_ok=True)
    json.dump(inv, open(os.path.join(a.out, 'licenses-inventory.json'), 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=1)
    lines = ['# 部品のライセンスの集計（collect_licenses.py が作った．手で直さない）', '']
    for kind in ('npm', 'python', 'cargo'):
        es = [e for e in inv if e['kind'] == kind]
        if not es:
            continue
        c = collections.Counter(e['license'] or '(なし)' for e in es)
        lines += [f'## {kind}（{len(es)} 個）', '', '| ライセンス | 数 |', '|---|---:|']
        lines += [f'| {k} | {v} |' for k, v in c.most_common()]
        chk = [e for e in es if e['check']]
        lines += ['', f'確かめが要る物: {len(chk)} 個', '']
        lines += [f'- `{e["name"]}@{e["version"]}`（{e["license"] or "記載なし"}）: {e["check"]}．`{e["path"]}`' for e in chk]
        lines.append('')
    open(os.path.join(a.out, 'licenses-summary.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    print(f'{len(inv)} 個を集めた → {a.out}')
    for kind in ('npm', 'python', 'cargo'):
        es = [e for e in inv if e['kind'] == kind]
        print(f'  {kind}: {len(es)} 個，確かめが要る {sum(1 for e in es if e["check"])} 個')
    return 0


if __name__ == '__main__':
    sys.exit(main())
