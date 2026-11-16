#!/usr/bin/env python3
"""Sync-Strata の配布物を組み立てる（作者の PC で流す．利用者の PC ではビルドしない）．

  py -3 -X utf8 build_pack.py --sources ../sources.json --out <出力フォルダー> [--zip] [--release 0.1.0-1115]

出力（= 利用者が落として展開する物）:
  <out>/SyncStrata-<release>/
    setup.cmd                 ダブルクリックで入れる（初回・修復・友人の PC のどれも同じ 1 つ）
    README.md                 利用者向けの説明書
    installer/installer.ps1   setup・update・rollback・uninstall の本体（部品 pack にも同じ物が入る）
    feed/manifest.json        版の一覧（部品ごとの版・sha256・大きさ・置き場）
    feed/components/<id>-<版>.zip
  <out>/SyncStrata-<release>.zip   （--zip のとき．上のフォルダーを 1 つにまとめた物）

部品の zip の中には _pkg/component.json（id・版・files_sha256）と _pkg/files.tsv（道のり・大きさ・sha256）を入れる．
files_sha256 は files.tsv の sha256．setup はこれで「入っている物と一覧が同じか」を決める（zip の sha256 は運ぶ途中の確かめ）．

最後に，配布物の全ファイルからこの PC の利用者名・PC の名前・ホームの道のり・作業場の道のりを探す（--deny-file で足せる）．
見つかったら一覧を出して終了コード 3（--allow-private で 0 のまま）．
"""
import argparse, fnmatch, hashlib, io, json, os, re, shutil, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
SRC = os.path.join(PACK, 'src')
FIXED_TIME = (2026, 1, 1, 0, 0, 0)     # zip の中の時刻は固定（同じ中身なら同じ zip になる）
DEFAULT_EXCLUDE = ['__pycache__/*', '*/__pycache__/*', '*.pyc', '*.bak-*', '*.bak', '*.log', '.git/*', '*/.git/*']


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def collect(comp, base):
    """部品の元の置き場から (zip の中の道のり, 元のファイル) を集める．"""
    out = {}
    excl = DEFAULT_EXCLUDE + comp.get('exclude', [])
    for fr in comp['from']:
        src = os.path.normpath(os.path.join(base, fr['src']))
        dst = fr.get('dst', '').strip('/')
        if os.path.isfile(src):
            out[(dst + '/' if dst else '') + os.path.basename(src) if not fr.get('as') else fr['as']] = src
            continue
        if not os.path.isdir(src):
            raise SystemExit(f"{comp['id']}: 元の置き場が無い: {src}")
        for root, dirs, files in os.walk(src):
            dirs.sort()
            for fn in sorted(files):
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, src).replace(os.sep, '/')
                if any(fnmatch.fnmatch(rel, e) for e in excl):
                    continue
                out[(dst + '/' if dst else '') + rel] = p
    if not out:
        raise SystemExit(f"{comp['id']}: ファイルが 1 つも無い")
    bad = [r for r in out if r.startswith('_pkg/')]
    if bad:
        raise SystemExit(f"{comp['id']}: _pkg/ は配布の道具が使う名前: {bad[:3]}")
    return dict(sorted(out.items()))


def build_component(comp, base, outdir, level):
    t0 = time.time()
    files = collect(comp, base)
    rows, total = [], 0
    for rel, p in files.items():
        size = os.path.getsize(p)
        total += size
        rows.append(f'{rel.replace("/", chr(92))}\t{size}\t{sha256_file(p)}')
    tsv = ('\n'.join(rows) + '\n').encode('utf-8')
    files_sha = hashlib.sha256(tsv).hexdigest()
    meta = {'id': comp['id'], 'name': comp['name'], 'version': comp['version'], 'files': len(rows), 'installed_bytes': total,
            'files_sha256': files_sha}
    # 11/16 S2: Linux で実行できるようにするファイル（部品の exec の型．zip の中の道のり）．setup が chmod +x する
    execs = sorted(r for r in files if any(fnmatch.fnmatch(r, e) for e in comp.get('exec', [])))
    name = f"{comp['id']}-{comp['version']}.zip"
    zp = os.path.join(outdir, 'components', name)
    os.makedirs(os.path.dirname(zp), exist_ok=True)
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED, compresslevel=level) as z:
        def put(arc, data=None, src=None):
            zi = zipfile.ZipInfo(arc, FIXED_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = (0o755 if arc in execs else 0o644) << 16
            if src is None:
                z.writestr(zi, data)
            else:
                with open(src, 'rb') as f, z.open(zi, 'w', force_zip64=True) as w:
                    shutil.copyfileobj(f, w, 8 << 20)
        put('_pkg/component.json', json.dumps(meta, ensure_ascii=False, indent=1).encode('utf-8'))
        put('_pkg/files.tsv', tsv)
        if execs:
            put('_pkg/exec.txt', ('\n'.join(execs) + '\n').encode('utf-8'))
        for rel, p in files.items():
            put(rel, src=p)
    entry = dict(meta)
    entry.update({'place': comp.get('place', 'app'), 'archive': f'components/{name}', 'size': os.path.getsize(zp), 'sha256': sha256_file(zp)})
    for k in ('entry', 'what', 'variant'):     # 11/15 S2: variant＝世代ごとのエンジン（setup が GPU に合う 1 つだけ入れる）
        if comp.get(k):
            entry[k] = comp[k]
    print(f"  {comp['id']:9s} {comp['version']:14s} {len(rows):>6,} ファイル  {total / 2**20:8.1f} MB → zip {entry['size'] / 2**20:8.1f} MB  ({time.time() - t0:.1f} 秒)", flush=True)
    return entry


def deny_patterns(extra_file, sources):
    pats = set()
    for k in ('USERNAME', 'COMPUTERNAME'):
        v = os.environ.get(k)
        if v and len(v) >= 3:
            pats.add(v)
    home = os.environ.get('USERPROFILE')
    if home:
        pats.add(home); pats.add(home.replace('\\', '/'))
    for c in sources['components']:      # 作業場の道のり（<作業場> のような，元の置き場の頭 2 段）
        for fr in c['from']:
            p = os.path.normpath(os.path.join(sources['_base'], fr['src']))
            parts = p.split(os.sep)
            if len(parts) >= 2 and re.match(r'^[A-Za-z]:$', parts[0]):
                head = parts[0] + '\\' + parts[1]
                skip = ('c:' + chr(92) + 'windows', 'c:' + chr(92) + 'program files', 'c:' + chr(92) + 'users')
                if not os.path.normcase(head).startswith(skip) and not os.path.normcase(head).startswith(os.path.normcase(os.path.join(os.environ.get('TEMP', ''), ''))):
                    pats.add(head); pats.add(head.replace('\\', '/'))
    if extra_file and os.path.exists(extra_file):
        for l in open(extra_file, encoding='utf-8'):
            l = l.strip()
            if l and not l.startswith('#'):
                pats.add(l)
    return sorted(pats, key=len, reverse=True)


def _allow_re():
    """公開のアカウント名（pack/tools/allow.words.txt）を完全一致で消すための正規表現（11/16）"""
    import re as _re
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "allow.words.txt")
    ws = [l.strip().lower() for l in open(f, encoding="utf-8")] if os.path.exists(f) else []
    ws = sorted({w for w in ws if w and not w.startswith("#")}, key=len, reverse=True)
    if not ws:
        return None
    alt = "|".join(_re.escape(w) for w in ws)
    return [_re.compile(("(?<![a-z0-9])(?:" + alt + ")(?![a-z0-9])").encode()),
            _re.compile(("(?<![a-z0-9])(?:" + alt + ")(?![a-z0-9])").encode("utf-16-le"))]


ALLOW = _allow_re()


def allow_strip(low):
    for rx in ALLOW or []:
        low = rx.sub(b" ", low)
    return low


def scan_private(root, pats):
    """配布物の全ファイル（zip は中身まで）から pats を探す（大文字小文字を区別しない．UTF-8 と UTF-16 の両方）．"""
    needles = []
    for p in pats:
        for enc in ('utf-8', 'utf-16-le'):
            needles.append((p, p.lower().encode(enc)))
    hits = {}

    def look(name, data):
        low = allow_strip(data.lower())     # 11/16: 公開のアカウント名は完全一致で許す
        for p, n in needles:
            if n in low:
                hits.setdefault(p, []).append(name)

    for r, ds, fs in os.walk(root):
        for fn in fs:
            fp = os.path.join(r, fn)
            rel = os.path.relpath(fp, root)
            if fn.endswith('.zip'):
                with zipfile.ZipFile(fp) as z:
                    for zi in z.infolist():
                        look(f'{rel}!{zi.filename}', zi.filename.encode('utf-8') + b'\n' + z.read(zi))
            else:
                look(rel, open(fp, 'rb').read())
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sources', default=os.path.join(PACK, 'sources.json'))
    ap.add_argument('--out', required=True)
    ap.add_argument('--release')
    ap.add_argument('--platform', choices=('windows', 'linux'), default='windows',
                    help='11/16 S2: 組む OS．部品の os（windows｜linux．無ければ両方）で選ぶ．Linux は setup.sh と installer/installer.py')
    ap.add_argument('--zip', action='store_true', help='配布物を 1 つの zip にもまとめる')
    ap.add_argument('--level', type=int, default=6, help='zip の圧縮の強さ（0〜9）')
    ap.add_argument('--deny-file', default=os.path.join(HERE, 'deny.local.txt'), help='探す文字列を足す（1 行 1 つ．配布物には入れない）')
    ap.add_argument('--allow-private', action='store_true')
    ap.add_argument('--no-scan', action='store_true')
    a = ap.parse_args()
    t0 = time.time()
    sp = os.path.abspath(a.sources)
    sources = json.load(open(sp, encoding='utf-8'))
    sources['_base'] = os.path.dirname(sp)
    release = a.release or sources['release']
    dist = os.path.join(os.path.abspath(a.out), f'SyncStrata-{release}' + ('' if a.platform == 'windows' else '-linux'))
    if os.path.exists(dist):
        shutil.rmtree(dist)
    feed = os.path.join(dist, 'feed')
    os.makedirs(feed)
    print(f'配布物 {release} → {dist}')
    comps = []
    skipped = []
    for c in sources['components']:
        if c.get('os', a.platform) != a.platform:
            continue
        if c.get('optional') and not all(os.path.exists(os.path.normpath(os.path.join(sources['_base'], fr['src']))) for fr in c['from']):
            skipped.append(c['id'])
            print(f"  {c['id']:9s} （元の置き場がまだ無いので入れない: optional）")
            continue
        comps.append(build_component(c, sources['_base'], feed, a.level))
    manifest = {
        'product': 'sync-strata', 'schema': 1, 'release': release, 'platform': 'windows-x64' if a.platform == 'windows' else 'linux-x64',
        'built': time.strftime('%Y-%m-%dT%H:%M:%S'),
        # 11/16 S2: 更新の置き場（GitHub のリリース）．sources.json の github_account の 1 か所で差し替える（{github_account}・{release} を埋める）
        'update_feed': sources.get('update_feed', '').replace('{github_account}', sources.get('github_account', '{account}')).replace('{release}', release),
        'release_feed': sources.get('release_feed', '').replace('{github_account}', sources.get('github_account', '{account}')).replace('{release}', release),
        'places': {'app': {'default': '~/.local/share/SyncStrata', 'what': 'アプリの部品（app/<id>/）．update で入れ替え，前の版を app/.prev/ に 1 つ残す'},
                   'models': {'default': 'settings.json の models_dir（無ければ ~/.local/share/SyncStrata/models）', 'what': 'モデル．setup・update は落とし直さない・消さない'},
                   'user': {'default': '$SYNC_HOME，無ければ ~/.config/SyncStrata', 'what': '設定（settings.json）・dsh の設定と会話（dsh-home/）．update・rollback は触らない'},
                   } if a.platform == 'linux' else {
            'app': {'default': '%LOCALAPPDATA%\\Programs\\SyncStrata', 'what': 'アプリの部品（app\\<id>\\）．update で入れ替え，前の版を app\\.prev\\ に 1 つ残す'},
            'models': {'default': 'settings.json の models_dir（setup が探して書く）', 'what': 'モデル．setup・update は落とし直さない・消さない'},
            'user': {'default': '%SYNC_HOME%，無ければ %LOCALAPPDATA%\\SyncStrata', 'what': '設定（settings.json）・dsh の設定と会話（dsh-home\\）．update・rollback は触らない'},
        },
        'shortcuts': sources.get('shortcuts' if a.platform == 'windows' else 'shortcuts_linux', []),
        'components': comps,
    }
    with open(os.path.join(feed, 'manifest.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.makedirs(os.path.join(dist, 'installer'))
    if a.platform == 'windows':
        shutil.copy2(os.path.join(SRC, 'setup.cmd'), os.path.join(dist, 'setup.cmd'))
        shutil.copy2(os.path.join(SRC, 'installer', 'installer.ps1'), os.path.join(dist, 'installer', 'installer.ps1'))
    else:
        # 11/16 決定: Linux の setup は係 L の pack/src/installer/setup.sh（sh だけ）に一本化．配布物の直下の setup.sh はそれだけ
        # （S2 の installer.py と pack/src/setup.sh は入れない．両方を持つと直しがずれるため）
        if not os.path.exists(os.path.join(SRC, 'installer', 'setup.sh')):
            raise SystemExit('Linux の setup.sh（pack/src/installer/setup.sh）が無い')
        for f, d in [(os.path.join('installer', 'setup.sh'), 'setup.sh')]:
            with open(os.path.join(SRC, f), 'rb') as r:
                data = r.read().replace(b'\r\n', b'\n')
            with open(os.path.join(dist, d), 'wb') as w:
                w.write(data)
    readme = os.path.join(SRC, 'README.md' if a.platform == 'windows' else 'README.linux.md')
    if os.path.exists(readme):
        shutil.copy2(readme, os.path.join(dist, 'README.md'))
    rc = 0
    if not a.no_scan:
        pats = deny_patterns(a.deny_file, sources)
        t1 = time.time()
        hits = scan_private(dist, pats)
        print(f'私的な文字列の検査: {len(pats)} 種 × UTF-8/UTF-16（{time.time() - t1:.1f} 秒）→ ' + ('見つからない' if not hits else f'{len(hits)} 種が見つかった'))
        for p, where in hits.items():
            print(f'  !! {"*" * 3}{p[-4:]}（{len(p)} 字）: {len(where)} か所．例: {where[:3]}')
        if hits and not a.allow_private:
            rc = 3
    if a.zip:
        t1 = time.time()
        zp = dist + '.zip'
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_STORED) as z:   # 中の部品は圧縮済みなので，外側はまとめるだけ
            # 11/15 S2: main_zip が false の部品（Radeon・GTX 10 用のエンジンなど）は配布の zip に入れない（更新の置き場に別に置き，setup が要るときだけ取る）
            outside = {os.path.normcase(os.path.join(feed, c['archive'].replace('/', os.sep))) for c in comps
                       if not next((x for x in sources['components'] if x['id'] == c['id'] and x.get('os', a.platform) == a.platform), {}).get('main_zip', True)}
            for r, ds, fs in os.walk(dist):
                for fn in sorted(fs):
                    fp = os.path.join(r, fn)
                    if os.path.normcase(fp) in outside:
                        continue
                    arc = os.path.join(os.path.basename(dist), os.path.relpath(fp, dist)).replace(os.sep, '/')
                    if a.platform == 'linux' and fn.endswith(('.sh', '.py')):     # Linux: setup.sh などに実行の印
                        zi = zipfile.ZipInfo(arc, time.localtime(os.path.getmtime(fp))[:6])
                        zi.external_attr = 0o755 << 16
                        with open(fp, 'rb') as f:
                            z.writestr(zi, f.read())
                    else:
                        z.write(fp, arc)
        print(f'まとめ: {zp}（{os.path.getsize(zp) / 2**20:.1f} MB，{time.time() - t1:.1f} 秒）')
    tot = sum(c['size'] for c in comps)
    print(f'部品 {len(comps)} 個，zip の合計 {tot / 2**20:.1f} MB，展開後 {sum(c["installed_bytes"] for c in comps) / 2**20:.1f} MB，{time.time() - t0:.1f} 秒')
    return rc


if __name__ == '__main__':
    sys.exit(main())
