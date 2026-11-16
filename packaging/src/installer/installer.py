#!/usr/bin/env python3
"""Sync-Strata の Linux の setup・update・rollback・uninstall・status（11/16 係 S2．Windows の installer.ps1 と同じ形）．
標準ライブラリだけ（setup.sh が，この PC の python3 か，配布物の同梱の Python で流す）．

  python3 installer.py setup  [--source <feed>] [--app-dir DIR] [--sync-home DIR] [--models-dir DIR] [--shortcut-dir DIR]
                              [--no-shortcuts] [--no-model-search] [--full] [--report FILE]
  python3 installer.py update [--source <feed|URL>] [--force]
  python3 installer.py rollback | uninstall [--yes] [--remove-data] | status [--full]

置き場（XDG の決まり．INTERFACE.md の 7）:
  アプリ   --app-dir（既定 $XDG_DATA_HOME/SyncStrata＝~/.local/share/SyncStrata）の app/<部品>/．update で入れ替え，前の版を app/.prev/ に 1 つ
  利用者   SYNC_HOME（既定 $XDG_CONFIG_HOME/SyncStrata＝~/.config/SyncStrata）．settings.json・dsh-home/．update・rollback は触らない
  モデル   settings.json の models_dir（既定 ~/.local/share/SyncStrata/models）．落とし直さない・消さない（uninstall は聞く）
部品の zip の中: _pkg/component.json・_pkg/files.tsv（道のりは Windows の区切り \\）・_pkg/exec.txt（chmod +x する物）．
世代ごとのエンジン（一覧の variant）は，起動の道具の sync env が選んだ 1 つだけ入れる．手元に無い zip は，setup の隣（展開した
フォルダーかその 1 つ上）→ 一覧の update_feed（URL）の順に探す．
終了コード: 0＝成功，5＝一覧と合わない zip を断った，6＝失敗，7＝動いているので入れ替えなかった．
"""
import argparse, hashlib, json, os, re, shutil, stat, subprocess, sys, time, urllib.request, zipfile

A = None
RESULTS, COMPS = [], []
EXIT = {"code": 0, "refused": False}


def say(s):
    print(s, flush=True)


def add(tag, what):
    RESULTS.append(f"  [{tag}] {what}")


def xdg(var, default):
    return os.environ.get(var) or os.path.expanduser(default)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_json(p, default=None):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(o, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def rmtree(p):
    if os.path.lexists(p):
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)


def cmp_version(a, b):
    pa, pb = re.split(r"[.\-+]", a or ""), re.split(r"[.\-+]", b or "")
    for i in range(max(len(pa), len(pb))):
        x = pa[i] if i < len(pa) else ""
        y = pb[i] if i < len(pb) else ""
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return (int(x) > int(y)) - (int(x) < int(y))
        if x == "":
            return 1
        if y == "":
            return -1
        return (x > y) - (x < y)
    return 0


# ---------------------------------------------------------------- 置き場と記録
def paths():
    app = os.path.abspath(A.app_dir or os.environ.get("SYNC_APP_DIR") or os.path.join(xdg("XDG_DATA_HOME", "~/.local/share"), "SyncStrata"))
    home = os.path.abspath(A.sync_home or os.environ.get("SYNC_HOME") or os.path.join(xdg("XDG_CONFIG_HOME", "~/.config"), "SyncStrata"))
    return {"app": app, "bin": os.path.join(app, "app"), "prev": os.path.join(app, "app", ".prev"), "stage": os.path.join(app, "app", ".stage"),
            "state_dir": os.path.join(app, "state"), "state": os.path.join(app, "state", "state.json"), "home": home,
            "settings": os.path.join(home, "settings.json")}


def read_state(P):
    s = read_json(P["state"])
    if not s or s.get("product") != "sync-strata":
        s = {"product": "sync-strata", "schema": 1, "release": "", "components": {}, "prev": {}, "last_update": None, "skip": {},
             "shortcuts": [], "feed": ""}
    for k in ("components", "prev", "skip"):
        s.setdefault(k, {})
    s.setdefault("shortcuts", [])
    return s


# ---------------------------------------------------------------- 版の一覧と zip
class Feed:
    def __init__(self, src):
        self.url = bool(re.match(r"^https?://", src))
        if self.url:
            murl = src if src.endswith(".json") else src.rstrip("/") + "/manifest.json"
            self.m = json.loads(urllib.request.urlopen(murl, timeout=60).read().decode("utf-8-sig"))
            self.base = murl[:murl.rindex("/") + 1]
        else:
            mp = src if src.endswith(".json") else os.path.join(src, "manifest.json")
            if not os.path.exists(mp):
                raise RuntimeError(f"版の一覧が無い: {mp}")
            self.m = read_json(mp)
            self.base = os.path.dirname(os.path.abspath(mp))
        if self.m.get("product") != "sync-strata" or self.m.get("schema") != 1:
            raise RuntimeError(f"Sync-Strata の版の一覧ではない（product・schema が違う）: {src}")
        if self.m.get("platform") not in (None, "linux-x64"):
            raise RuntimeError(f"この一覧は {self.m.get('platform')} 用（Linux 用の配布物の setup.sh を使う）")
        self.where = src


def get_archive(P, feed, c):
    rel = c["archive"]
    name = os.path.basename(rel)
    dl = os.path.join(P["state_dir"], "download")
    p = None
    if feed.url:
        os.makedirs(dl, exist_ok=True)
        p = os.path.join(dl, name)
        if not (os.path.exists(p) and os.path.getsize(p) == c["size"] and sha256(p) == c["sha256"]):
            download(feed.base + name, p, c)
    else:
        p = os.path.normpath(os.path.join(feed.base, rel))
        if not os.path.exists(p):
            # 手で落とした zip を setup の隣（展開したフォルダーか，その 1 つ上）に置けば，それを使う
            for d in (DIST_ROOT, os.path.dirname(DIST_ROOT) if DIST_ROOT else None):
                if d and os.path.exists(os.path.join(d, name)):
                    p = os.path.join(d, name)
                    break
        if not os.path.exists(p):
            uf = feed.m.get("update_feed") or ""
            if not re.match(r"^https?://", uf):
                raise RuntimeError(f"部品の zip が無い: {p}（更新の置き場も決まっていない）")
            os.makedirs(dl, exist_ok=True)
            p = os.path.join(dl, name)
            say(f"   {c['id']} は手元に無いので更新の置き場から取ります（{c['size'] / 2**20:,.0f} MB）")
            if not (os.path.exists(p) and os.path.getsize(p) == c["size"]):
                download(uf.rstrip("/") + "/" + name, p, c)
    if os.path.getsize(p) != c["size"]:
        EXIT["refused"] = True
        raise RuntimeError(f"{c['id']}: zip の大きさが一覧と違う（{os.path.getsize(p)}，一覧 {c['size']}）")
    h = sha256(p)
    if h != c["sha256"]:
        EXIT["refused"] = True
        raise RuntimeError(f"{c['id']}: zip の sha256 が一覧と違う（{h}）")
    return p


def download(url, p, c):
    tmp = p + ".part"
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 8 << 20)
    os.replace(tmp, p)


# ---------------------------------------------------------------- 部品を調べる・入れる
def tsv_rows(d):
    with open(os.path.join(d, "_pkg", "files.tsv"), encoding="utf-8") as f:
        for l in f:
            l = l.rstrip("\n")
            if l:
                rel, size, h = l.split("\t")
                yield rel.replace("\\", "/"), int(size), h


def read_scan(p):
    out = {}
    try:
        for l in open(p, encoding="utf-8"):
            k, _, v = l.rstrip("\n").partition("\t")
            out[k] = v
    except OSError:
        pass
    return out


def write_scan(d, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as w:
        for rel, size, h in tsv_rows(d):
            fp = os.path.join(d, rel)
            if os.path.exists(fp):
                st = os.stat(fp)
                w.write(f"{rel}\t{st.st_size}\t{st.st_mtime_ns}\n")


def test_component(d, scan_path, full, sizes_only=False):
    r = {"state": "missing", "version": "", "files_sha256": "", "files": 0, "bad": [], "hashed": 0}
    if not os.path.isdir(d):
        return r
    meta, lst = os.path.join(d, "_pkg", "component.json"), os.path.join(d, "_pkg", "files.tsv")
    if not (os.path.exists(meta) and os.path.exists(lst)):
        r.update(state="broken", bad=["_pkg"])
        return r
    m = read_json(meta, {})
    r["version"], r["files_sha256"] = m.get("version", ""), m.get("files_sha256", "")
    if sha256(lst) != r["files_sha256"]:
        r.update(state="broken", bad=["_pkg/files.tsv"])
        return r
    scan = {} if full else read_scan(scan_path)
    bad = []
    for rel, size, h in tsv_rows(d):
        r["files"] += 1
        fp = os.path.join(d, rel)
        if not os.path.isfile(fp) or os.path.getsize(fp) != size:
            bad.append(rel)
            continue
        if sizes_only:
            continue
        st = os.stat(fp)
        if scan.get(rel) == f"{st.st_size}\t{st.st_mtime_ns}":
            continue
        r["hashed"] += 1
        if sha256(fp) != h:
            bad.append(rel)
    r["bad"], r["state"] = bad, ("broken" if bad else "ok")
    return r


def plan_for(c, have, S):
    if have["state"] == "missing":
        return "install", "新規"
    if have["state"] == "broken":
        if have["version"] == c["version"]:
            return "repair", f"壊れていた {len(have['bad'])} ファイルを含めて入れ直す"
        return "install", f"壊れていた {have['version']} を {c['version']} に"
    k = cmp_version(have["version"], c["version"])
    if k > 0:
        return "skip", f"入っている {have['version']} の方が新しい"
    if k < 0:
        if S["skip"].get(c["id"]) == c["version"] and not A.force:
            return "skip", f"{c['version']} は戻した版なので入れない（--force で入れる）"
        return "install", f"{have['version']} → {c['version']}"
    if have["files_sha256"] != c["files_sha256"]:
        return "install", f"同じ版 {c['version']} の作り直し"
    return "skip", "そろっている"


def install_component(P, c, zp, keep_prev):
    cid = c["id"]
    stage = os.path.join(P["stage"], cid)
    rmtree(stage)
    os.makedirs(stage)
    with zipfile.ZipFile(zp) as z:
        for zi in z.infolist():
            name = zi.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise RuntimeError(f"{cid}: zip の中の道のりがおかしい: {name}")
            z.extract(zi, stage)
    # Windows の区切りで入った道のり（files.tsv は \\）を / に
    t = test_component(stage, "", False, True)
    if t["state"] != "ok" or t["files_sha256"] != c["files_sha256"] or t["version"] != c["version"]:
        rmtree(stage)
        EXIT["refused"] = True
        raise RuntimeError(f"{cid} の中身が一覧と合わない（{t['state']}，違うファイル {len(t['bad'])}）")
    ex = os.path.join(stage, "_pkg", "exec.txt")
    if os.path.exists(ex):
        for l in open(ex, encoding="utf-8"):
            fp = os.path.join(stage, l.strip())
            if l.strip() and os.path.isfile(fp):
                os.chmod(fp, os.stat(fp).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    dest = os.path.join(P["bin"], cid)
    if os.path.exists(dest):
        if keep_prev:
            pv = os.path.join(P["prev"], cid)
            os.makedirs(P["prev"], exist_ok=True)
            rmtree(pv)
            os.rename(dest, pv)
            sp = os.path.join(P["state_dir"], f"{cid}.scan.tsv")
            if os.path.exists(sp):
                os.replace(sp, os.path.join(P["state_dir"], f"prev-{cid}.scan.tsv"))
        else:
            rmtree(dest)
    os.rename(stage, dest)
    write_scan(dest, os.path.join(P["state_dir"], f"{cid}.scan.tsv"))
    return t


def app_processes(P):
    """入れた先の app/ の下の実行ファイルで動いているプロセス（/proc/*/exe）"""
    root = os.path.realpath(P["bin"]) + "/"
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                exe = os.path.realpath(os.readlink(f"/proc/{d}/exe"))
            except OSError:
                continue
            if exe.startswith(root):
                out.append((int(d), exe))
    return out


def assert_not_running(P, what):
    ps = app_processes(P)
    if ps:
        say(f"\n!! Sync-Strata が動いているので{what}ません（使っているファイルは入れ替えられない）:")
        for pid, exe in ps:
            say(f"     番号 {pid} {exe[len(os.path.realpath(P['bin'])) + 1:]}")
        say("   アプリを「全て閉じる」で閉じるか，sync.sh down --all を流してから，もう一度．")
        EXIT["code"] = 7
        return False
    return True


def sync_components(P, S, feed, is_update, variants=False):
    plans = []
    for c in feed.m["components"]:
        v = c.get("variant") or ""
        if variants:
            if not v or v != ENGINE["variant"]:
                continue
        elif v:
            continue
        t0 = time.time()
        have = test_component(os.path.join(P["bin"], c["id"]), os.path.join(P["state_dir"], f"{c['id']}.scan.tsv"), A.full)
        act, why = plan_for(c, have, S)
        plans.append((c, have, act, why, time.time() - t0))
    if any(x[2] != "skip" for x in plans) and not assert_not_running(P, "入れ替え"):
        for c, have, act, why, _ in plans:
            add("飛ばした" if act == "skip" else "止めた", f"{c['id']} {c['version']}（{why}）")
        return
    changed, frm, to = [], {}, {}
    for c, have, act, why, chk in plans:
        cid = c["id"]
        rec = {"id": cid, "action": act, "from": have["version"], "to": c["version"], "check_s": round(chk, 2), "files": c["files"],
               "bytes": c["installed_bytes"], "install_s": 0}
        if act == "skip":
            add("飛ばした", f"{cid} {c['version']}（{why}．調べ {chk:.1f} 秒）")
            COMPS.append(rec)
            continue
        t0 = time.time()
        try:
            say(f"== {cid}（{c['name']}）: {why}")
            zp = get_archive(P, feed, c)
            keep = act == "install" and have["state"] != "missing"
            install_component(P, c, zp, keep)
            if feed.url:
                try:
                    os.remove(zp)
                except OSError:
                    pass
            if keep:
                S["prev"][cid] = {"version": have["version"], "files_sha256": have["files_sha256"]}
                changed.append(cid)
                frm[cid], to[cid] = have["version"], c["version"]
            S["components"][cid] = {"version": c["version"], "files_sha256": c["files_sha256"], "sha256": c["sha256"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            rec["install_s"] = round(time.time() - t0, 2)
            add({"install": "入れた", "repair": "直した"}[act], f"{cid} {c['version']}（{why}．{c['files']:,} ファイル {c['installed_bytes'] / 2**20:,.0f} MB．{time.time() - t0:.1f} 秒）")
        except Exception as e:
            rec["action"] = "failed"
            add("失敗", f"{cid} {c['version']}: {e}（前の版のまま）")
            if not EXIT["code"]:
                EXIT["code"] = 5 if EXIT["refused"] else 6
        COMPS.append(rec)
    if changed:
        S["last_update"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "ids": changed, "from": frm, "to": to, "command": A.command}
    S["release"] = feed.m.get("release", "")
    rmtree(P["stage"])


ENGINE = {"variant": None}
DIST_ROOT = None


def launcher_python(P):
    py = os.path.join(P["bin"], "python", "bin", "python3")
    sy = os.path.join(P["bin"], "launcher", "sync.py")
    if not os.path.exists(sy):
        return None, None
    return (py if os.path.exists(py) else sys.executable), sy      # 同梱の Python が無ければ setup を流している python3


def env_check(P):
    py, sy = launcher_python(P)
    if not py:
        return None
    try:
        e = dict(os.environ, SYNC_HOME=P["home"])
        out = subprocess.run([py, "-s", "-X", "utf8", sy, "env", "--json"], env=e, capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        return json.loads(out.strip().splitlines()[-1])
    except Exception:
        return None


def show_env(P):
    j = env_check(P)
    if not j:
        add("注意", "対応環境を調べられませんでした")
        return
    add("対応" if j.get("ok") else "対応外", "この PC で使えます" if j.get("ok") else "この PC では使えません（アプリは入れました）")
    for b in j.get("blockers") or []:
        add("対応外", b.get("text", b.get("key")))
    for w in (j.get("warnings") or []) + (j.get("notes") or []):
        add("注意", w.get("text", w.get("key")))


# ---------------------------------------------------------------- アイコン・入口・dsh の設定・モデル
def desktop_dir():
    try:
        d = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if d and d != os.path.expanduser("~"):
            return d
    except (OSError, subprocess.TimeoutExpired):
        pass
    return os.path.expanduser("~/Desktop")


def set_shortcuts(P, S, m):
    if A.shortcut_dir:
        dirs = {"desktop": os.path.join(A.shortcut_dir, "Desktop"), "startmenu": os.path.join(A.shortcut_dir, "applications")}
    else:
        dirs = {"desktop": desktop_dir(), "startmenu": os.path.join(xdg("XDG_DATA_HOME", "~/.local/share"), "applications")}
    made = []
    for sc in m.get("shortcuts") or []:
        target = os.path.join(P["app"], sc["target"])
        if sc.get("fallback") and not os.path.exists(target):
            target = os.path.join(P["app"], sc["fallback"])
        args = sc.get("args", "")
        icon = os.path.join(P["bin"], "launcher", "icon.png")
        text = ("[Desktop Entry]\nType=Application\nVersion=1.0\n"
                f"Name={sc['name']}\nComment={sc.get('description', sc['name'])}\n"
                f"Exec=\"{target}\"{(' ' + args) if args else ''}\nTerminal={'true' if sc.get('terminal') else 'false'}\n"
                + (f"Icon={icon}\n" if os.path.exists(icon) else "") + "Categories=Utility;\n")
        for w in sc.get("where", ["startmenu"]):
            d = dirs.get(w)
            if not d:
                continue
            os.makedirs(d, exist_ok=True)
            fn = re.sub(r"[^\w.-]+", "-", sc.get("file", sc["name"])).strip("-") + ".desktop"
            fp = os.path.join(d, fn)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(fp, 0o755)
            made.append(fp)
    S["shortcuts"] = sorted(set(S.get("shortcuts", []) + made))
    if made:
        add("作った", f"アイコン {len(made)} 個（{', '.join(os.path.basename(x) for x in made)}）")


STUB = """#!/bin/sh
# Sync-Strata: {what}. Runs a copy of the installer from a temporary folder, so that it can replace (or remove) this folder.
D="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"
cp "$D/app/pack/installer.py" "$T/installer.py" || {{ echo "The installer is missing: run setup.sh from the downloaded folder again."; exit 1; }}
PY="$D/app/python/bin/python3"; [ -x "$PY" ] || PY=python3
"$PY" "$T/installer.py" {cmd} --app-dir "$D" "$@"
RC=$?
rm -rf "$T"
exit $RC
"""


def set_stubs(P):
    made = []
    for cmd, what in (("update", "update (only the changed parts)"), ("uninstall", "uninstall"), ("rollback", "go back to the version before the last update")):
        p = os.path.join(P["app"], cmd + ".sh")
        text = STUB.format(what=what, cmd=cmd)
        if os.path.exists(p) and open(p).read() == text:
            continue
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.chmod(p, 0o755)
        made.append(cmd + ".sh")
    if made:
        add("作った", "入口 " + "，".join(made))


def set_dsh_profile(P):
    tpl = os.path.join(P["bin"], "pack", "dsh-profile")
    if not os.path.isdir(tpl):
        return
    dst = os.path.join(P["home"], "dsh-home", "profiles", "web")
    made = []
    for f in sorted(os.listdir(tpl)):
        name = re.sub(r"\.template$", "", f)
        p = os.path.join(dst, name)
        if os.path.exists(p):
            continue
        os.makedirs(dst, exist_ok=True)
        shutil.copyfile(os.path.join(tpl, f), p)
        made.append(name)
    add("作った" if made else "飛ばした", f"dsh の設定 {'，'.join(made)}（{dst}）" if made else "dsh の設定（もうある．触らない）")


def model_layout(P):
    cat = read_json(os.path.join(P["bin"], "chat", "models", "models.dist.json"))
    if not cat:
        return ["sync-s-sb", "sync-r1q2-sb"], []
    packs = [m["local_dir"] for m in cat.get("models", []) if not m.get("pending")]
    shared = [(s["id"], [os.path.normpath(os.path.join(s["local_dir"], f["path"])) for f in s.get("files") or []])
              for s in cat.get("shared", []) if not s.get("optional")]
    return packs, shared


def test_models_dir(P, d):
    r = {"dir": d, "packs": [], "missing_shared": []}
    if not d or not os.path.isdir(d):
        return r
    packs, shared = model_layout(P)
    for pk in packs:
        man = read_json(os.path.join(d, pk, "MANIFEST.json"))
        if not man:
            continue
        ok = True
        for name, v in (man.get("files") or {}).items():
            fp = os.path.join(d, pk, name)
            if not os.path.exists(fp) or (isinstance(v, dict) and v.get("bytes") is not None and os.path.getsize(fp) != v["bytes"]):
                ok = False
                break
        if ok:
            r["packs"].append(pk)
    for sid, files in shared:
        if any(not os.path.exists(os.path.join(d, f)) for f in files):
            r["missing_shared"].append(sid)
    return r


def model_candidates(P):
    c = []
    if os.environ.get("SYNC_MODELS"):
        c.append(os.environ["SYNC_MODELS"])
    if DIST_ROOT:
        c += [os.path.join(DIST_ROOT, "models"), os.path.join(os.path.dirname(DIST_ROOT), "models")]
    c += [os.path.join(xdg("XDG_DATA_HOME", "~/.local/share"), "SyncStrata", "models"), os.path.join(P["home"], "models")]
    home = os.path.expanduser("~")
    for b in (home, os.path.join(home, "Downloads"), os.path.join(home, "Desktop"), os.path.join(home, "Documents")):
        c.append(os.path.join(b, "models"))
        try:
            c += [os.path.join(b, x, "models") for x in sorted(os.listdir(b)) if os.path.isdir(os.path.join(b, x)) and not x.startswith(".")]
        except OSError:
            pass
    for root in ("/mnt", "/media/" + os.environ.get("USER", ""), "/data", "/srv"):
        try:
            for x in sorted(os.listdir(root)):
                c.append(os.path.join(root, x, "models"))
                c += [os.path.join(root, x, y, "models") for y in sorted(os.listdir(os.path.join(root, x)))[:200]]
        except OSError:
            pass
    return c


def find_models(P):
    st = read_json(P["settings"], {}) or {}
    cur = st.get("models_dir", "auto")
    t0 = time.time()
    if A.models_dir:
        found = test_models_dir(P, os.path.abspath(A.models_dir))
        if not found["packs"]:
            add("注意", f"指したモデルの置き場 {found['dir']} にはまだモデルが無い（書いておくので，アプリの案内で落とせる）")
    elif cur not in ("auto", "", None) and test_models_dir(P, cur)["packs"]:
        add("飛ばした", f"モデルの置き場（設定のまま {cur}．pack: {'，'.join(test_models_dir(P, cur)['packs'])}）")
        return
    elif A.no_model_search:
        add("飛ばした", "モデルの置き場を探す（--no-model-search）")
        return
    else:
        found, n = None, 0
        for d in dict.fromkeys(model_candidates(P)):
            n += 1
            if os.path.isdir(d):
                t = test_models_dir(P, d)
                if t["packs"]:
                    found = t
                    break
        if not found:
            add("なし", f"モデルの置き場は見つからなかった（{n} か所を {time.time() - t0:.1f} 秒で見た．アプリの最初の画面の案内で落とす）")
            return
    if cur != found["dir"]:
        st["models_dir"] = found["dir"]
        write_json(st, P["settings"])
    miss = f"．足りない共通の部品: {'，'.join(found['missing_shared'])}" if found["missing_shared"] else ""
    add("見つけた", f"モデルの置き場 {found['dir']}（pack: {'，'.join(found['packs']) or 'なし'}{miss}．settings.json の models_dir に書いた．落とし直さない）")


# ---------------------------------------------------------------- CPU の優先度の許可（任意．sudo が要る．11/16 エンジン 3 の材料）
NICE_FILES = [
    ("/etc/systemd/system/user@.service.d/90-sync-strata-nice.conf", "[Service]\nLimitNICE=-10\n"),
    ("/etc/systemd/user.conf.d/90-sync-strata-nice.conf", "[Manager]\nDefaultLimitNICE=-10\n"),
    ("/etc/security/limits.d/90-sync-strata.conf", "{user} - nice -10\n"),      # ssh・端末のログイン向け
]


def nice_allowed():
    """CPU の優先度を上げてよいか（ulimit -e が 30 以上＝nice -10 まで）"""
    try:
        import resource
        return resource.getrlimit(resource.RLIMIT_NICE)[0] >= 30
    except (ImportError, AttributeError, OSError, ValueError):
        return False


def nice_hint(apply=False):
    """許可が無ければ，打つコマンドを出す（setup は自分で sudo を打たない．--apply-nice のときだけ sudo で書く）．
    許可が無くてもエンジンはそのまま動く（優先度を上げないだけ）"""
    if nice_allowed():
        add("任意", "CPU の優先度を上げる許可: あり（ulimit -e が 30 以上）")
        return
    user = os.environ.get("USER") or os.path.basename(os.path.expanduser("~"))
    cmds = []
    for path, body in NICE_FILES:
        body = body.format(user=user)
        cmds.append(f"sudo mkdir -p {os.path.dirname(path)} && printf '{body.replace(chr(10), chr(92) + 'n')}' | sudo tee {path} >/dev/null")
    if apply:
        for c in cmds:
            r = subprocess.run(["sh", "-c", c])
            if r.returncode != 0:
                add("失敗", f"CPU の優先度の許可を書けませんでした（{c.split(' | ')[0]}）")
                return
        add("任意", "CPU の優先度の許可を書きました．PC を起動し直すと効きます（確かめ: ulimit -e が 30）")
        return
    add("任意", "ほかのアプリが CPU を使っているときの速さの落ちを抑えます（任意。sudo が要ります）．打つコマンド（PC の起動し直しで効く）:")
    for c in cmds:
        RESULTS.append("      " + c)
    RESULTS.append("      確かめ: 起動し直した後に ulimit -e が 30．エンジンの記録に「STRATA_QL_PRIO_CPU=above: nice 0 -> -5」．"
                   "setup.sh --apply-nice でも書けます（sudo のパスワードを聞きます）")


# ---------------------------------------------------------------- 命令
def main(argv=None):
    global A, DIST_ROOT
    ap = argparse.ArgumentParser(prog="installer.py")
    ap.add_argument("command", nargs="?", default="setup", choices=("setup", "update", "rollback", "uninstall", "status"))
    ap.add_argument("--source")
    ap.add_argument("--app-dir")
    ap.add_argument("--sync-home")
    ap.add_argument("--models-dir")
    ap.add_argument("--shortcut-dir")
    ap.add_argument("--no-shortcuts", action="store_true")
    ap.add_argument("--no-model-search", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--remove-data", action="store_true")
    ap.add_argument("--report")
    ap.add_argument("--apply-nice", action="store_true", help="CPU の優先度の許可を sudo で書く（任意．既定は打つコマンドを出すだけ）")
    A = ap.parse_args(argv)
    P = paths()
    S = read_state(P)
    t_start = time.time()
    try:
        if A.command == "setup":
            if not A.source:
                raise RuntimeError("setup には --source（版の一覧の置き場）が要る．setup.sh から流してください．")
            if not re.match(r"^https?://", A.source):
                DIST_ROOT = os.path.dirname(os.path.abspath(A.source.rstrip("/")))
            say(f"Sync-Strata の setup: 入れる先 {P['app']}")
            feed = Feed(A.source)
            os.makedirs(P["bin"], exist_ok=True)
            os.makedirs(P["state_dir"], exist_ok=True)
            sync_components(P, S, feed, False)
            j = env_check(P)
            ENGINE["variant"] = (j or {}).get("engine")
            if ENGINE["variant"] and EXIT["code"] != 7:
                sync_components(P, S, feed, False, True)
            elif not ENGINE["variant"]:
                add("飛ばした", "エンジン（この PC の GPU に合う物が無い．下の「対応外」を見る）")
            if EXIT["code"] != 7:
                set_stubs(P)
                S["feed"] = feed.m.get("update_feed", "")
                if not A.no_shortcuts:
                    set_shortcuts(P, S, feed.m)
                os.makedirs(P["home"], exist_ok=True)
                set_dsh_profile(P)
                find_models(P)
                show_env(P)
                nice_hint(A.apply_nice)
            write_json(S, P["state"])
        elif A.command == "update":
            if not os.path.exists(P["state"]):
                raise RuntimeError(f"Sync-Strata が入っていない（{P['app']}）．先に setup.sh を流してください．")
            src = A.source
            if not src:
                st = read_json(P["settings"], {}) or {}
                src = st.get("update_feed") if st.get("update_feed") not in (None, "", "auto") else S.get("feed")
            if not src:
                raise RuntimeError("更新の置き場が決まっていない: settings.json の update_feed にフォルダーか URL を書くか，update.sh --source <置き場> で．")
            say(f"Sync-Strata の update: 置き場 {src}")
            feed = Feed(src)
            sync_components(P, S, feed, True)
            j = env_check(P)
            ENGINE["variant"] = (j or {}).get("engine")
            if ENGINE["variant"] and EXIT["code"] != 7:
                sync_components(P, S, feed, True, True)
            write_json(S, P["state"])
        elif A.command == "rollback":
            lu = S.get("last_update")
            if not lu or not lu.get("ids"):
                say("戻せる物が無い（直前の update で入れ替えた部品が無い）．")
            elif assert_not_running(P, "戻し"):
                for cid in lu["ids"]:
                    cur, pv = os.path.join(P["bin"], cid), os.path.join(P["prev"], cid)
                    t = test_component(pv, "", True)
                    if t["state"] != "ok":
                        add("失敗", f"{cid}: 前の版が残っていない・壊れている（{t['state']}）")
                        EXIT["code"] = 6
                        continue
                    now = test_component(cur, "", False)
                    tmp = os.path.join(P["stage"], f"swap-{cid}")
                    os.makedirs(P["stage"], exist_ok=True)
                    rmtree(tmp)
                    os.rename(cur, tmp)
                    os.rename(pv, cur)
                    os.rename(tmp, pv)
                    write_scan(cur, os.path.join(P["state_dir"], f"{cid}.scan.tsv"))
                    write_scan(pv, os.path.join(P["state_dir"], f"prev-{cid}.scan.tsv"))
                    S["skip"][cid] = now["version"]
                    S["prev"][cid] = {"version": now["version"], "files_sha256": now["files_sha256"]}
                    S["components"][cid] = {"version": t["version"], "files_sha256": t["files_sha256"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                    add("戻した", f"{cid} {now['version']} → {t['version']}（{now['version']} は次の update でも入れない．入れるときは update --force）")
                S["last_update"] = None
                rmtree(P["stage"])
                write_json(S, P["state"])
        elif A.command == "uninstall":
            if not os.path.exists(P["state"]):
                raise RuntimeError(f"Sync-Strata の記録（state/state.json）が無いので消さない: {P['app']}")
            if assert_not_running(P, "消し"):
                st = read_json(P["settings"], {}) or {}
                md = st.get("models_dir") if st.get("models_dir") not in (None, "", "auto") else ""
                drop_m = drop_h = bool(A.remove_data)
                if not A.remove_data and not A.yes and sys.stdin.isatty():
                    if md and os.path.isdir(md):
                        drop_m = input(f"モデル（{md}）も消しますか？ 消すと次は落とし直しになります [y/N] ").strip().lower().startswith("y")
                    if os.path.isdir(P["home"]):
                        drop_h = input(f"設定と会話（{P['home']}）も消しますか？ [y/N] ").strip().lower().startswith("y")
                for l in S.get("shortcuts", []):
                    if os.path.exists(l):
                        os.remove(l)
                add("消した", f"アイコン {len(S.get('shortcuts', []))} 個")
                rmtree(P["app"])
                add("消した", f"アプリ {P['app']}")
                if md:
                    if drop_m:
                        rmtree(md)
                        add("消した", f"モデル {md}")
                    else:
                        add("残した", f"モデル {md}")
                if drop_h:
                    rmtree(P["home"])
                    add("消した", f"設定と会話 {P['home']}")
                elif os.path.isdir(P["home"]):
                    add("残した", f"設定と会話 {P['home']}")
        elif A.command == "status":
            for d in sorted(os.listdir(P["bin"])) if os.path.isdir(P["bin"]) else []:
                if d.startswith(".") or not os.path.isdir(os.path.join(P["bin"], d)):
                    continue
                t = test_component(os.path.join(P["bin"], d), os.path.join(P["state_dir"], f"{d}.scan.tsv"), A.full)
                pv = S["prev"].get(d)
                add(t["state"], f"{d} {t['version']}（{t['files']:,} ファイル{('．前の版 ' + pv['version'] + ' を残している') if pv else ''}）")
    except Exception as e:
        add("失敗", str(e))
        if not EXIT["code"]:
            EXIT["code"] = 5 if EXIT["refused"] else 6
    say("")
    say(f"結果（{A.command}．{time.time() - t_start:.1f} 秒）:")
    for l in RESULTS:
        say(l)
    if A.report:
        write_json({"command": A.command, "exit": EXIT["code"], "seconds": round(time.time() - t_start, 2), "lines": RESULTS, "components": COMPS}, A.report)
    return EXIT["code"]


if __name__ == "__main__":
    sys.exit(main())
