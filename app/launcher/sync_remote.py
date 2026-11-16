#!/usr/bin/env python3
"""スマホの接続（11/15 係 R．設定 lan_remote＝off｜lan｜tailscale．INTERFACE.md の 8）．

- 番地を決める（plan）:
    lan       この PC の既定の経路の IPv4（LAN の番地．Tailscale・リンクローカル・ループバックは除く）．0.0.0.0 では待ち受けない．
    tailscale `tailscale status --json` がログイン済み（BackendState Running）なら，その IPv4 と名前（MagicDNS）．
              入っていない・ログインしていないときは待ち受けず，短い案内だけ返す（入れる・ログインするのは本人）．
  受け付ける名前（Host）: 番地:番号，PC の名前:番号（lan は .local も），MagicDNS の名前:番号．
- sync_home.start_dsh から呼ばれる（差し込みの 2 行）:
    dsh_args(s)        dsh web に足す --trusted-host（dsh の自前の検査が LAN・Tailscale の名前を通すように）
    relay_env(s, env)  中継に渡す DSH_REMOTE_*（off のときは消す）．決めた番地は SYNC_HOME\\run\\remote.json（秘密は無し）
- CLI（sync.py から）:
    sync remote-url [--json]          今つなげる URL（トークン・合い言葉は出さない）
    sync remote-url --pair [--json]   PC の画面なしでスマホをつなぐ: 1 回きり・3 分の合い言葉入りの URL と QR を端末に出す（記録しない）
    sync remote-apply                 設定を今すぐ効かせる: 自分で起こした dsh と中継だけを起こし直す（エンジンと会話の中継はそのまま）
"""
import json, os, re, shutil, socket, subprocess, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oscompat  # noqa: E402,F401  11/16 S2: Linux では creationflags を外す

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sync_home as H  # noqa: E402

NO_WINDOW = 0x08000000
_plans = {}


def _ip_ok(ip, mode):
    try:
        a = [int(x) for x in ip.split(".")]
    except ValueError:
        return False
    if len(a) != 4 or a[0] in (0, 127) or (a[0] == 169 and a[1] == 254) or a[0] >= 224:
        return False
    cgnat = a[0] == 100 and 64 <= a[1] <= 127          # Tailscale の番地（100.64.0.0/10）
    return cgnat if mode == "tailscale" else not cgnat


def lan_ip():
    """既定の経路の IPv4（UDP の connect だけ．何も送らない）．使えなければ名前から引いた番地の中の私的な物"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.0.2.1", 9))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if _ip_ok(ip, "lan"):
            return ip
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if _ip_ok(ip, "lan") and (ip.startswith(("192.168.", "10.")) or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", ip)):
                return ip
    except OSError:
        pass
    return None


def tailscale_exe():
    p = os.environ.get("SYNC_TAILSCALE") or shutil.which("tailscale")
    if p:
        return p
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base and os.path.isfile(os.path.join(base, "Tailscale", "tailscale.exe")):
            return os.path.join(base, "Tailscale", "tailscale.exe")
    return None


def tailscale_self():
    """{ip, names, problem}．problem: not_installed｜not_running（ログインしていない・止まっている）｜None"""
    exe = tailscale_exe()
    if not exe:
        return {"ip": None, "names": [], "problem": "not_installed"}
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, encoding="utf-8", timeout=8, creationflags=NO_WINDOW).stdout
        d = json.loads(out or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"ip": None, "names": [], "problem": "not_running"}
    me = d.get("Self") or {}
    ip = next((x for x in me.get("TailscaleIPs") or [] if _ip_ok(x, "tailscale")), None)
    if d.get("BackendState") != "Running" or not ip:
        return {"ip": None, "names": [], "problem": "not_running"}
    names = []
    dns = str(me.get("DNSName") or "").rstrip(".").lower()
    if dns:
        names += [dns, dns.split(".")[0]]
    return {"ip": ip, "names": names, "problem": None}


def _name_ok(n):
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*", n))


def plan(s, fresh=False):
    """この起動の接続の決め方．{mode, setting, port, bind:[ip], names:[host:port], urls, problem}（秘密は入れない）"""
    mode = s.get("lan_remote") or "off"
    port = int(s["relay_port"])
    key = (mode, port)
    if key in _plans and not fresh:
        return _plans[key]
    p = {"mode": mode, "setting": mode, "port": port, "bind": [], "names": [], "urls": [], "problem": None}
    hosts = []
    if mode == "lan":
        ip = lan_ip()
        if ip:
            pc = socket.gethostname().lower()
            hosts = [ip] + ([pc, pc + ".local"] if _name_ok(pc) else [])
            p["bind"] = [ip]
        else:
            p["problem"] = "no_lan"
    elif mode == "tailscale":
        t = tailscale_self()
        if t["ip"]:
            hosts = [t["ip"]] + [n for n in t["names"] if _name_ok(n)]
            p["bind"] = [t["ip"]]
        p["problem"] = t["problem"]
    if not p["bind"]:
        p["mode"] = "off"
    seen = []
    for h in hosts:
        if f"{h}:{port}" not in seen:
            seen.append(f"{h}:{port}")
    p["names"] = seen
    p["urls"] = [f"http://{n}/m/" for n in seen]
    _plans[key] = p
    return p


def _write(name, d):
    f = H.path("run", name)
    with open(f + ".tmp", "w", encoding="utf-8") as w:
        json.dump(d, w, ensure_ascii=False, indent=1)
    os.replace(f + ".tmp", f)


def dsh_args(s):
    """dsh web に足す引数（--trusted-host を名前ごとに）．決めた名前を run\\remote-dsh.json に残す（中継と食い違ったら起こし直しが要る）"""
    p = plan(s)
    _write("remote-dsh.json", {"names": p["names"], "at": time.time()})
    out = []
    for n in p["names"]:
        out += ["--trusted-host", n]
    return out


def relay_env(s, env):
    """中継に渡す環境変数を env に入れる（off なら DSH_REMOTE_* を消して 127.0.0.1 だけ）"""
    for k in [k for k in env if k.startswith("DSH_REMOTE_")]:
        env.pop(k)
    p = plan(s)
    _write("remote.json", {**p, "at": time.time()})
    env["DSH_REMOTE_MODE"] = p["mode"]
    if p["mode"] != "off":
        env["DSH_REMOTE_BIND"] = ",".join(p["bind"])
        env["DSH_REMOTE_NAMES"] = ",".join(p["names"])
        env["DSH_REMOTE_RUN"] = os.path.dirname(H.path("run", "x"))
    return env


# ------------------------------------------------------------------ CLI
TEXT = {
    "off": "スマホの接続は切ってあります（sync settings set lan_remote lan か tailscale）．",
    "no_lan": "LAN の番地が見つかりません．PC が Wi-Fi か有線の LAN につながっているか確かめてください．",
    "not_installed": "この PC に Tailscale が入っていません．tailscale.com から入れてログインし，sync remote-apply．",
    "not_running": "この PC の Tailscale がログインしていないか止まっています．ログインしてから sync remote-apply．",
    "restart": "設定と今の待ち受けが違います．sync remote-apply で dsh と中継を起こし直すと効きます．",
    "relay_down": "中継が動いていません（sync up で起こすと効きます）．",
    "lan_http": "同じ Wi-Fi の中は暗号化されません（http）．家など信頼できる Wi-Fi で使ってください．",
    "fw": "つながらないとき: スマホと PC が同じ Wi-Fi か／Windows のファイアウォールで dsh-node.exe（Node.js）がプライベートで許可されているか／PC の Wi-Fi がプライベートになっているか．",
    "fw_ts": "つながらないとき: スマホにも Tailscale を入れて同じアカウントでログインしているか／Windows のファイアウォールで dsh-node.exe（Node.js）が許可されているか．",
    # 11/16 S2: Linux の案内（Windows のファイアウォールの代わり）
    "fw_linux": "つながらないとき: スマホと PC が同じ Wi-Fi か／ファイアウォール（ufw など）で中継の番号が LAN から許可されているか．",
    "fw_ts_linux": "つながらないとき: スマホにも Tailscale を入れて同じアカウントでログインしているか／ファイアウォールで tailscale0 からの中継の番号が許可されているか．",
}


def _relay(s, path, post=False):
    """中継（127.0.0.1）に CLI の鍵で聞く．鍵の無いとき（off・中継が古い）は None"""
    try:
        key = open(os.path.join(H.home(), "run", "remote-key"), encoding="utf-8").read().strip()
    except OSError:
        return None
    port = s["relay_port"]
    hdr = {"x-sync-remote-key": key, "Host": f"127.0.0.1:{port}"}
    if post:
        hdr.update({"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"})
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"{}" if post else None, headers=hdr, method="POST" if post else "GET")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=8).read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            return {"ok": False, "error": f"HTTP {e.code}"}
    except (OSError, ValueError):
        return None


def view(s):
    """remote-url の中身（トークン・合い言葉は入れない）"""
    setting = s.get("lan_remote") or "off"
    relay_up = H.listening(s["relay_port"])
    live = _relay(s, "/m/remote/status") if relay_up else None
    try:
        used = json.load(open(os.path.join(H.home(), "run", "remote.json"), encoding="utf-8"))
    except (OSError, ValueError):
        used = None
    p = plan(s)
    out = {"setting": setting, "mode": "off", "live": False, "urls": [], "url": None, "problem": None, "notes": [], "relay_up": relay_up}
    if live and live.get("ok") and live.get("mode") != "off" and any(l.get("up") for l in live.get("listening") or []):
        out.update(mode=live["mode"], live=True, urls=live.get("urls") or [])
    if setting == "off":
        out["problem"] = None if not out["live"] else "restart"
    elif p["problem"]:
        out["problem"] = p["problem"]
    elif not relay_up:
        out["problem"] = "relay_down"
    elif not out["live"] or out["mode"] != setting or (used and used.get("names") != p["names"]):
        out["problem"] = "restart"
    if not out["urls"] and setting != "off" and not p["problem"]:
        out["urls"] = p["urls"]           # まだ待ち受けていない: 起こし直した後の URL
    out["url"] = out["urls"][0] if out["urls"] else None
    m = out["mode"] if out["live"] else setting
    if m == "lan":
        out["notes"] += ["lan_http", "fw" if os.name == "nt" else "fw_linux"]
    elif m == "tailscale":
        out["notes"] += ["fw_ts" if os.name == "nt" else "fw_ts_linux"]
    return out


def _qr_terminal(rows):
    """QR を端末に描く（上下 2 マスを 1 文字で．白地に黒．余白 2 マス）"""
    n = len(rows)
    q = 2
    get = lambda x, y: 0 <= x < n and 0 <= y < n and rows[y][x] == "1"
    os.system("")   # Windows の端末で色の指定を効かせる
    lines = []
    for y in range(-q, n + q, 2):
        line = ""
        for x in range(-q, n + q):
            top, bot = get(x, y), get(x, y + 1)
            line += " " if not top and not bot else "▀" if top and not bot else "▄" if bot and not top else "█"
        lines.append("\x1b[30;47m" + line + "\x1b[0m")
    return "\n".join(lines)


def cmd_remote_url(argv):
    s = H.effective()
    v = view(s)
    if "--pair" in argv:
        if not v["live"]:
            msg = TEXT.get(v["problem"] or "off", TEXT["off"])
            print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False) if "--json" in argv else msg)
            return 1
        r = _relay(s, "/m/remote/pair", post=True)
        if not r or not r.get("ok"):
            msg = (r or {}).get("error") or "中継に聞けませんでした"
            print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False) if "--json" in argv else msg)
            return 1
        if "--json" in argv:
            print(json.dumps({"ok": True, "pair_url": r["url"], "expires_in": r["expires_in"], "qr": r["qr"]}, ensure_ascii=False))
            return 0
        print(_qr_terminal(r["qr"]["rows"]))
        print(f"スマホのカメラで読むと会話の画面が開きます（1 回きり．{r['expires_in'] // 60} 分で切れます）．")
        print(r["url"])
        for k in v["notes"]:
            print("  " + TEXT[k])
        return 0
    if "--json" in argv:
        print(json.dumps({**v, "problem_text": TEXT.get(v["problem"]) if v["problem"] else None, "notes_text": [TEXT[k] for k in v["notes"]]}, ensure_ascii=False))
        return 0
    if v["problem"]:
        print(TEXT.get(v["problem"], v["problem"]))
    for u in v["urls"]:
        print(u)
    if v["live"] and v["urls"]:
        print("（スマホで初めて開くときは，PC の画面の「起動の設定」の QR か sync remote-url --pair で）")
    for k in v["notes"]:
        print("  " + TEXT[k])
    return 0 if v["urls"] or v["setting"] == "off" else 1


def cmd_remote_apply(argv):
    """自分で起こした dsh と中継を起こし直す（会話の中継とエンジンはそのまま）．常駐の dsh には触れない"""
    s = H.effective()
    if H.listening(s["dsh_port"]) and not H.alive("dsh"):
        print(f"dsh（{s['dsh_port']}）は自分で起こした物ではないので，起こし直せません．")
        return 1
    time.sleep(0.5)    # 中継から呼ばれたとき: 中継が答えを返し終えるのを待つ
    if H.procs().get("dsh-node"):
        H.stop("dsh-node")
    for name in ("dsh", "relay"):
        H.stop(name)
    for port in (s["dsh_port"], s["relay_port"]):
        t0 = time.time()
        while H.listening(port) and time.time() - t0 < 15:
            time.sleep(0.3)
    ok = H.start_dsh(s)
    v = view(s)
    print("起こし直しました．" if ok else "起こし直せませんでした（SYNC_HOME\\logs を見てください）．")
    for u in v["urls"]:
        print(u)
    return 0 if ok else 1


def main(cmd, argv):
    if cmd == "remote-url":
        return cmd_remote_url(argv)
    if cmd == "remote-apply":
        return cmd_remote_apply(argv)
    print("使い方: sync remote-url [--json] [--pair] ／ sync remote-apply")
    return 2
