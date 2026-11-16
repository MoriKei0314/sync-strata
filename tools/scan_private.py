#!/usr/bin/env python3
"""公開する物に個人の情報が残っていないかを調べる（係 D，11/15．係 P の build_pack.py と S2 の scan_dist.py の検査が土台）．読むだけ．

  py -3 -X utf8 scan_private.py [--target <フォルダーか zip> ...] [--sources <sources.json>] [--words <語のファイル> ...]
                               [--max-mb 256] [--json <結果の JSON>] [--show-context]

調べる物（--target も --sources も無いとき）:
  1. 公開の文書の案（このファイルの 1 つ上の publish/．_local/ と licenses-inventory/ の中の道のりは除く）
  2. sources.json の部品の元の置き場（build_pack.py と同じ除外）＝ zip に入る前の配布物そのもの
探す物（3 種．どれも大文字小文字を区別しない．UTF-8 と UTF-16LE の両方）:
  A. 語: 環境変数の利用者名・PC の名前・ホームの道のり・作業場の道のり（build_pack.deny_patterns）
         ＋ --words のファイル（1 行 1 語．既定は publish/_local/deny.words.txt と pack/tools/deny.local.txt）
  B. 形: メールアドレス・ユーザーのフォルダーの道のり（Users のフォルダー<名前>，/home/<名前>）・鍵の形（hf_… ghp_… など，秘密鍵の頭）
  C. ドライブの道のり（Windows の標準の置き場 を除く．文字のファイルだけ）
出力には見つかった語そのものを書かない（末尾 4 字と長さだけ）．--show-context は手元で直す人のためだけに使う．
組んだ後の配布物（zip を展開したフォルダー，または zip そのもの．中の部品の zip も開いて見る）:
  py -3 -X utf8 scan_private.py --target <out>/SyncStrata-<版>      （zip なら --target <out>/SyncStrata-<版>.zip）
  部品（node_modules・Python・DLL・ライセンスの束）の中のメール・ユーザーのフォルダーは「部品由来」として数だけ出す．
終了コード: 0＝見つからない（部品由来だけを含む），3＝見つかった．
"""
import argparse, collections, fnmatch, json, os, re, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLISH = os.path.dirname(HERE)
APP = os.path.dirname(PUBLISH)
PACK = os.path.join(APP, 'pack')
sys.path.insert(0, os.path.join(PACK, 'tools'))
import build_pack as BP  # noqa: E402

TEXT_EXT = ('.py', '.ps1', '.cmd', '.bat', '.json', '.mjs', '.js', '.cjs', '.ts', '.html', '.css', '.md', '.txt', '.yml', '.yaml',
            '.toml', '.webmanifest', '.jinja', '.tsv', '.csv', '.xml', '.ini', '.cfg')
SHAPES = {
    'メールアドレス': re.compile(rb'[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,12}'),
    'ユーザーのフォルダー': re.compile(rb'(?i)(?:[A-Z]:[\\/]{1,2}Users[\\/]{1,2}(?!Public|Default|All Users|<|%|\$|\{)[A-Za-z0-9._-]{2,}'
                                 rb'|/home/(?!runner|user|<|\$|\{)[a-z0-9._-]{2,}|/Users/(?!Shared|<|\$|\{)[A-Za-z0-9._-]{2,})'),
    '鍵の形': re.compile(rb'(?:\bhf_[A-Za-z0-9]{30,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|\bsk-[A-Za-z0-9]{32,}'
                       rb'|-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b)'),
}
# よく出る，個人に結び付かない住所（部品の作者の公開の連絡先など）は件数だけ別に数える
MAIL_SKIP = re.compile(rb'(?i)@(?:users\.noreply\.github\.com|example\.(?:com|org|net)|localhost|python\.org|nvidia\.com|'
                       rb'notice\.qwencloud\.com|npmjs\.com|apache\.org|mozilla\.org|gnu\.org|fsf\.org)$')
DRIVE = re.compile(rb'(?<![A-Za-z])([A-Za-z]):(\\{1,2}|/)(?=[A-Za-z$%])')
SELF_SKIP = ('_local/', 'licenses-inventory/')
# 部品（他人の作った物）の中の場所: ここでの B（メール・ユーザーのフォルダー）は作者の連絡先や例文なので「部品由来」として別に数える．
# A（語）・鍵の形・自前のファイルの B はどこでも「直す物」．
THIRD_PARTY = re.compile(r'(?i)(node_modules/|site-packages/|python/Lib/|(^|[/!])licenses/|LICENSE|NOTICE|THIRD-PARTY|'
                         r'cublas|dsh-node\.exe|python3?\d*\.(dll|zip)|libcrypto|libssl|sqlite3\.dll|\.dist-info/)')


def words(files, sources):
    pats = set(BP.deny_patterns(None, sources)) if sources else set()
    for k in ('USERNAME', 'COMPUTERNAME'):
        v = os.environ.get(k)
        if v and len(v) >= 3:
            pats.add(v)
    h = os.environ.get('USERPROFILE')
    if h:
        pats.update([h, h.replace(chr(92), '/')])
    for f in files:
        if f and os.path.exists(f):
            for l in open(f, encoding='utf-8'):
                l = l.strip()
                if l and not l.startswith('#'):
                    pats.add(l)
    return sorted(pats, key=len, reverse=True)


_EXC = None


def _exception(where, data):
    """s2/scan_exceptions.json の部品（zip の中の名前と sha256 が両方合う物）なら，その記録（kinds）．無ければ None"""
    global _EXC
    if _EXC is None:
        f = os.path.join(APP, "s2", "scan_exceptions.json")
        _EXC = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else []
    name = where.replace(chr(92), "/").rsplit("!", 1)[-1].rsplit("/", 1)[-1]
    for e in _EXC:
        if e["member"] == name and __import__("hashlib").sha256(data).hexdigest() == e["sha256"]:
            return e
    return None


def mask(p):
    return f'***{p[-4:]}（{len(p)} 字）' if len(p) > 4 else f'***（{len(p)} 字）'


class Scan:
    def __init__(self, pats, max_bytes, ctx):
        self.needles = [(p, p.lower().encode(e)) for p in pats for e in ('utf-8', 'utf-16-le')]
        self.max = max_bytes
        self.ctx = ctx
        self.hits = []          # (種類, 中身の印, どこ, 前後)
        self.skipped = []
        self.files = 0

    def look(self, where, data, is_text):
        self.files += 1
        low = BP.allow_strip(data.lower())     # 11/16: 公開のアカウント名（pack/tools/allow.words.txt）は完全一致で許す
        exc = _exception(where, data)          # 11/16: 確かめた部品の当たり（s2/scan_exceptions.json）
        for p, n in self.needles:
            i = low.find(n)
            if i >= 0 and not (exc and 'A 語' in exc['kinds']):
                self.hits.append(('A 語', mask(p), where, self._c(data, i, len(n))))
        for kind, rx in SHAPES.items():
            for m in rx.finditer(data):
                s = m.group(0)
                if kind == 'メールアドレス' and (MAIL_SKIP.search(s) or re.search(rb'\.(?:png|jpg|svg|js|css|json|ts|node|dll)$', s, re.I)):
                    continue
                k2 = 'B ' + kind
                if kind != '鍵の形' and THIRD_PARTY.search(where.replace(chr(92), '/')):
                    k2 += '（部品由来）'
                self.hits.append((k2, f'（{len(s)} 字）', where, self._c(data, m.start(), len(s))))
        if is_text:
            for m in DRIVE.finditer(data):
                if m.group(1).upper() == b'C' and data[m.end():m.end() + 7].lower() == b'windows':
                    continue
                self.hits.append(('C ドライブの道のり', '', where, self._c(data, m.start(), 3)))

    def _c(self, data, i, n):
        if not self.ctx:
            return ''
        return data[max(0, i - 30):i + n + 30].decode('utf-8', 'replace').replace('\n', ' ')

    def path(self, fp, rel):
        if os.path.getsize(fp) > self.max:
            self.skipped.append((rel, os.path.getsize(fp)))
            return
        if fp.lower().endswith('.zip'):
            with zipfile.ZipFile(fp) as z:
                for zi in z.infolist():
                    if zi.file_size > self.max:
                        self.skipped.append((f'{rel}!{zi.filename}', zi.file_size))
                        continue
                    self.look(f'{rel}!{zi.filename}', zi.filename.encode() + b'\n' + z.read(zi), zi.filename.lower().endswith(TEXT_EXT))
            return
        with open(fp, 'rb') as f:
            self.look(rel, os.path.basename(fp).encode('utf-8') + b'\n' + f.read(), fp.lower().endswith(TEXT_EXT))

    def tree(self, root, label, excl=()):
        if os.path.isfile(root):
            self.path(root, label)
            return
        for r, ds, fs in os.walk(root):
            ds.sort()
            for fn in sorted(fs):
                fp = os.path.join(r, fn)
                rel = os.path.relpath(fp, root).replace(os.sep, '/')
                if any(fnmatch.fnmatch(rel, e) for e in excl):
                    continue
                self.path(fp, f'{label}/{rel}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', action='append', default=[])
    ap.add_argument('--sources', default=None)
    ap.add_argument('--words', action='append', default=None)
    ap.add_argument('--max-mb', type=float, default=256)
    ap.add_argument('--json')
    ap.add_argument('--exclude', action='append', default=[], help='--target の中で飛ばす相対の道のりの型（例: build-*/*，.git/*）')
    ap.add_argument('--show-context', action='store_true')
    ap.add_argument('--list-third-party', action='store_true', help='部品由来の当たりも 1 件ずつ並べる（既定は数だけ）')
    a = ap.parse_args()
    src_path = a.sources or os.path.join(PACK, 'sources.json')   # 語（作業場の道のり）はいつも sources から作る
    sources = None
    if src_path:
        sources = json.load(open(src_path, encoding='utf-8'))
        sources['_base'] = os.path.dirname(os.path.abspath(src_path))
    wf = a.words if a.words is not None else [os.path.join(PUBLISH, '_local', 'deny.words.txt'), os.path.join(PACK, 'tools', 'deny.local.txt')]
    pats = words(wf, sources or {'components': [], '_base': APP})
    sc = Scan(pats, int(a.max_mb * 2**20), a.show_context)
    if a.target:
        for t in a.target:
            sc.tree(t, os.path.basename(os.path.normpath(t)), excl=BP.DEFAULT_EXCLUDE + a.exclude)
    else:
        sc.tree(PUBLISH, 'publish', excl=[s + '*' for s in SELF_SKIP])
        for c in sources['components']:
            excl = BP.DEFAULT_EXCLUDE + c.get('exclude', [])
            for fr in c['from']:
                src = os.path.normpath(os.path.join(sources['_base'], fr['src']))
                if not os.path.exists(src):
                    continue
                sc.tree(src, f"{c['id']}:{fr.get('dst') or fr.get('as') or os.path.basename(src)}", excl=excl)
    third = [h for h in sc.hits if h[0].endswith('（部品由来）')]
    if not a.list_third_party:
        sc.hits = [h for h in sc.hits if not h[0].endswith('（部品由来）')]
    print(f'部品由来（メール・ユーザーのフォルダー．作者の連絡先や例文）: {len(third)} か所' + ('' if a.list_third_party else '（--list-third-party で並べる）'))
    by = collections.Counter((h[0], h[2].split('/')[0].split('!')[0]) for h in sc.hits)
    kinds = collections.Counter(h[0] for h in sc.hits)
    print(f'調べたファイル {sc.files:,}（大きすぎて飛ばした {len(sc.skipped)}），検査の語 {len(pats)} 種＋形 {len(SHAPES)} 種＋ドライブの道のり')
    print('見つかった数（種類ごと）: ' + ('なし' if not kinds else '，'.join(f'{k} {v}' for k, v in sorted(kinds.items()))))
    for (k, top), v in sorted(by.items()):
        print(f'  {k:14s} {top}: {v}')
    files = collections.defaultdict(list)
    for k, m, w, c in sc.hits:
        files[w].append((k, m, c))
    for w, items in list(files.items())[:400]:
        print(f'  - {w}: ' + '，'.join(sorted(set(f'{k} {m}' for k, m, c in items))))
        if a.show_context:
            for k, m, c in items[:3]:
                print(f'      …{c}…')
    for rel, size in sc.skipped:
        print(f'  （飛ばした {size / 2**20:.0f} MB）{rel}')
    if a.json:
        json.dump({'files': sc.files, 'patterns': len(pats), 'kinds': kinds,
                   'hits': [{'kind': k, 'mark': m, 'where': w} for k, m, w, c in sc.hits],
                   'skipped': sc.skipped}, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return 3 if sc.hits else 0   # 部品由来だけなら 0


if __name__ == '__main__':
    sys.exit(main())
