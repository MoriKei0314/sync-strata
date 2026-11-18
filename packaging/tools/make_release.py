#!/usr/bin/env python3
"""11/17 H（strata-engine2-desktop）: Windows と Linux の配布物を，GitHub のリリースに上げる 1 つの平らな置き場に並べる．
上げるのはこの道具ではしない（上げる・配るのは本人に確かめてから，別の手で）．

  py -3 -X utf8 make_release.py --win <out>/SyncStrata-<版> --linux <out-linux>/SyncStrata-<版>-linux --out <置き場> [--copy]

並べる物:
  manifest-windows-x64.json・manifest-linux-x64.json  OS ごとの一覧（0.1.1 からの配布の道具と update.cmd・update.sh が読む名前）
  manifest.json        Windows の一覧の写し（0.1.0-1115 の Windows の update.cmd が読む名前．0.1.0-1115 の Linux の setup.sh は
                       platform が違うので断る＝間違って Windows の部品を入れることはない）
  部品の zip           両方の OS の feed/components（main_zip でない部品も）．同じ名前は同じバイトであることを確かめる（違えば止まる）
  SyncStrata-<版>.zip・SyncStrata-<版>-linux.zip   build_pack --zip のまとめ（あれば）
  update.cmd・update.sh   1 本で動く更新の道具（部品 pack の zip の中の物をそのまま．0.1.0-1115 から上げるときはこれを落として流す）
  SHA256SUMS.txt
確かめ: 2 つの一覧の release が同じ・platform が正しい，一覧の部品の zip の大きさと sha256，名前のぶつかり，GitHub の 1 ファイルの上限（2 GiB）．
既定はハードリンク（同じドライブ．大きな zip を写さない）．--copy で写す．
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile

LIMIT = 2 * 1024 ** 3


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def put(src, dst, copy):
    if os.path.exists(dst):
        os.remove(dst)
    if not copy:
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--win', required=True, help='Windows の配布物のフォルダー（SyncStrata-<版>）')
    ap.add_argument('--linux', required=True, help='Linux の配布物のフォルダー（SyncStrata-<版>-linux）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--copy', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if os.listdir(a.out):
        raise SystemExit(f'置き場が空ではない: {a.out}（前の版の物と混ざらないよう，空のフォルダーを指す）')
    plan = {}          # 名前 → (元, sha256, どこから)
    mans = {}
    bad = []

    def add(name, src, where, h=None):
        h = h or sha256(src)
        if name in plan:
            if plan[name][1] != h:
                bad.append(f'{name}: {plan[name][2]} と {where} で中身が違う（同じ名前は同じ中身でないといけない）')
            return
        if os.path.getsize(src) >= LIMIT:
            bad.append(f'{name}: {os.path.getsize(src):,} バイトは GitHub の 1 ファイルの上限（2 GiB）を超える')
        plan[name] = (src, h, where)

    for plat, d in (('windows-x64', a.win), ('linux-x64', a.linux)):
        mp = os.path.join(d, 'feed', 'manifest.json')
        m = json.load(open(mp, encoding='utf-8'))
        if m.get('product') != 'sync-strata' or m.get('platform') != plat:
            raise SystemExit(f'{mp}: {plat} の一覧ではない（platform {m.get("platform")}）')
        mans[plat] = m
        for c in m['components']:
            zp = os.path.join(d, 'feed', *c['archive'].split('/'))
            h = sha256(zp)
            if os.path.getsize(zp) != c['size'] or h != c['sha256']:
                bad.append(f'{plat} {c["id"]}: zip が一覧と違う（{zp}）')
                continue
            add(os.path.basename(zp), zp, plat, h)
        add(f'manifest-{plat}.json', mp, plat)
        top = os.path.basename(os.path.normpath(d)) + '.zip'
        zp = os.path.join(os.path.dirname(os.path.normpath(d)), top)
        if os.path.exists(zp):
            add(top, zp, plat)
        else:
            print(f'  （まとめの zip が無い: {zp}．build_pack の --zip で作る）')
        # 更新の道具は部品 pack の zip の中の物（その版の配布の道具と同じ物）
        pc = next(c for c in m['components'] if c['id'] == 'pack')
        tool = 'update.cmd' if plat == 'windows-x64' else 'update.sh'
        with zipfile.ZipFile(os.path.join(d, 'feed', *pc['archive'].split('/'))) as z:
            if tool not in z.namelist():
                bad.append(f'{plat}: 部品 pack（{pc["version"]}）に {tool} が無い')
            else:
                tp = os.path.join(a.out, '.' + tool)
                with z.open(tool) as r, open(tp, 'wb') as w:
                    shutil.copyfileobj(r, w)
                add(tool, tp, plat + ' の pack')
    if mans['windows-x64']['release'] != mans['linux-x64']['release']:
        bad.append(f'版が違う: Windows {mans["windows-x64"]["release"]}，Linux {mans["linux-x64"]["release"]}')
    add('manifest.json', os.path.join(a.win, 'feed', 'manifest.json'), 'windows-x64（0.1.0-1115 の Windows の update.cmd 向けの写し）')
    if bad:
        for b in bad:
            print('!!', b)
        for t in ('.update.cmd', '.update.sh'):
            if os.path.exists(os.path.join(a.out, t)):
                os.remove(os.path.join(a.out, t))
        return 1
    for name, (src, h, where) in sorted(plan.items()):
        put(src, os.path.join(a.out, name), a.copy or src.startswith(a.out))
    for t in ('.update.cmd', '.update.sh'):
        if os.path.exists(os.path.join(a.out, t)):
            os.remove(os.path.join(a.out, t))
    with open(os.path.join(a.out, 'SHA256SUMS.txt'), 'w', encoding='utf-8', newline='\n') as f:
        for name, (src, h, where) in sorted(plan.items()):
            f.write(f'{h}  {name}\n')
    rel = mans['windows-x64']['release']
    tot = sum(os.path.getsize(os.path.join(a.out, n)) for n in plan)
    print(f'リリース {rel}: {len(plan) + 1} ファイル（SHA256SUMS.txt を含む），合計 {tot / 2**20:,.1f} MB → {a.out}')
    for name in sorted(plan):
        print(f'  {name:48s} {os.path.getsize(os.path.join(a.out, name)) / 2**20:10.1f} MB  {plan[name][2]}')
    print(f'上げるときの注意: タグは v{rel}．prerelease にしない（…/releases/latest/download は prerelease を見ないので，update が新しい版を見つけない）．'
          '置き場は平らに（フォルダーを作らない）．非公開のあいだは update は gh（見えるアカウントでログイン）か手で置いた zip で取る．')
    return 0


if __name__ == '__main__':
    sys.exit(main())
