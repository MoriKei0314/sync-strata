#!/usr/bin/env python3
"""dsh web の見張り（11/15 app1115．sync_home.start_dsh が窓なしで起こす）．

  python dsh_host.py --url-file <run\\dsh-url.json> --log <logs\\dsh.log> -- <node> <dsh の bin.js> web --no-open --port N

dsh を子として起こし，その標準出力を 1 行ずつ読む．「dsh web: <URL>」の行（ログイン用のトークン入り）だけは，
URL を url-file（この利用者だけが読めるフォルダー）に置き，記録には「dsh web: <伏せた>」と書く．ほかの行はそのまま記録へ．
子の番号は procs.json に「dsh-node」として残す（down --dsh がそれを止める）．子が終われば，この見張りも同じ終了コードで終わる．
"""
import argparse, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oscompat  # noqa: E402,F401  11/16 S2: Linux では creationflags を外す

ap = argparse.ArgumentParser()
ap.add_argument("--url-file", required=True)
ap.add_argument("--log", required=True)
ap.add_argument("cmd", nargs=argparse.REMAINDER)
A = ap.parse_args()
cmd = A.cmd[1:] if A.cmd and A.cmd[0] == "--" else A.cmd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_home as H  # noqa: E402

p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=0x08000000)
H.remember("dsh-node", p.pid)
TOKEN = re.compile(r"([?&](?:token|access_token)=)[^&#\s]+", re.I)
with open(A.log, "a", encoding="utf-8") as log:
    for raw in p.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        m = re.match(r"^dsh web: (http\S+)", line)
        if m:
            tmp = A.url_file + ".tmp"
            json.dump({"url": m.group(1)}, open(tmp, "w", encoding="utf-8"))
            os.replace(tmp, A.url_file)
        log.write(TOKEN.sub(r"\1<伏せた>", line) + "\n")
        log.flush()
sys.exit(p.wait())
