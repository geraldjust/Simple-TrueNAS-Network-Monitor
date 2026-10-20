#!/usr/bin/env python3
"""Simple TrueNAS Network Monitor v1.0.0: read-only Linux TCP monitor."""
import collections
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

VERSION = "1.0.0"
PORT = int(os.getenv("PORT", "8090"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
STATIC = Path(__file__).parent / "static"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / "history.db"
LOCK = threading.Lock()
STATE = {"version": VERSION, "timestamp": 0, "interfaces": {}, "clients": [],
         "totals": {"rx": 0, "tx": 0}, "error": None}
PORTS = {445:"SMB",3260:"iSCSI",2049:"NFS",22:"SSH",80:"HTTP",443:"HTTPS",
         32400:"Plex",111:"RPC",873:"rsync",548:"AFP",8080:"HTTP",8090:"HTTP",
         139:"SMB",5900:"VNC",3389:"RDP",53:"DNS",3306:"MySQL",5432:"PostgreSQL"}
LINE = re.compile(r"^ESTAB\s+\d+\s+\d+\s+(\S+)\s+(\S+)")
SENT = re.compile(r"\bbytes_sent:(\d+)")
RECV = re.compile(r"\bbytes_received:(\d+)")

def endpoint(value):
    # ss may render IPv4-mapped IPv6: [::ffff:192.168.0.1]:445
    if value.startswith("[") and "]:" in value:
        host, port = value[1:].rsplit("]:", 1)
    else:
        host, port = value.rsplit(":", 1)
    if host.startswith("::ffff:"):
        host = host[7:]
    return host, int(port)

def socket_counters():
    out = subprocess.run(["ss", "-tin"], capture_output=True, text=True, timeout=8, check=True).stdout
    sockets = {}
    current = None
    def finish():
        if current and current.get("sent") is not None and current.get("recv") is not None:
            key = (current["local"], current["peer"])
            # aggregate even if several sockets have same endpoints
            a, b = sockets.get(key, (0, 0))
            sockets[key] = (a + current["recv"], b + current["sent"])
    for line in out.splitlines():
        match = LINE.match(line)
        if match:
            finish()
            current = {"local": match.group(1), "peer": match.group(2),
                       "sent": None, "recv": None}
        elif current:
            a, b = SENT.search(line), RECV.search(line)
            if a: current["sent"] = int(a.group(1))
            if b: current["recv"] = int(b.group(1))
    finish()
    return sockets

def interface_counters():
    results = {}
    for d in Path("/sys/class/net").iterdir():
        if d.name == "lo": continue
        try:
            rx = int((d/"statistics/rx_bytes").read_text())
            tx = int((d/"statistics/tx_bytes").read_text())
            results[d.name] = (rx, tx)
        except (OSError, ValueError): continue
    return results

def protocol(local, peer):
    lh, lp = endpoint(local)
    ph, pp = endpoint(peer)
    if lp in PORTS: return PORTS[lp]
    if pp in PORTS: return PORTS[pp]
    return "Other TCP"

def is_loopback(host):
    return host in ("::1", "127.0.0.1") or host.startswith("127.")

def setup_db():
    with sqlite3.connect(DB) as db:
        db.execute("CREATE TABLE IF NOT EXISTS history (ts INTEGER NOT NULL, iface TEXT NOT NULL, rx REAL NOT NULL, tx REAL NOT NULL, PRIMARY KEY(ts,iface))")
        db.execute("CREATE INDEX IF NOT EXISTS idx_history_iface ON history(iface,ts)")

def sampler():
    old_sockets, old_ifaces = {}, {}
    last = time.monotonic()
    last_store = 0
    while True:
        start = time.monotonic()
        try:
            sockets = socket_counters()
            ifaces = interface_counters()
            dt = max(start - last, 0.001)
            clients = collections.defaultdict(lambda: {"rx":0.0, "tx":0.0, "connections":0})
            for key, (rx, tx) in sockets.items():
                local, peer = key
                try:
                    host, _ = endpoint(peer)
                    if is_loopback(host): continue
                    name = protocol(local, peer)
                except (ValueError, IndexError): continue
                record = clients[(host, name)]
                record["connections"] += 1
                if key in old_sockets:
                    prx, ptx = old_sockets[key]
                    if rx >= prx: record["rx"] += (rx-prx)/dt/1e6
                    if tx >= ptx: record["tx"] += (tx-ptx)/dt/1e6
            interface_rates = {}
            for name, (rx, tx) in ifaces.items():
                prx, ptx = old_ifaces.get(name, (rx, tx))
                interface_rates[name] = {
                    "rx": max(0, rx-prx)/dt/1e6 if rx>=prx else 0,
                    "tx": max(0, tx-ptx)/dt/1e6 if tx>=ptx else 0,
                }
            rows = [{"ip":ip, "protocol":name, **value} for (ip,name),value in clients.items()]
            rows.sort(key=lambda c:c["rx"]+c["tx"], reverse=True)
            total_rx = sum(r["rx"] for r in rows)
            total_tx = sum(r["tx"] for r in rows)
            now = int(time.time())
            with LOCK:
                STATE.update(timestamp=now, interfaces=interface_rates, clients=rows,
                             totals={"rx":total_rx, "tx":total_tx}, error=None)
            if now-last_store >= 5:
                with sqlite3.connect(DB, timeout=5) as db:
                    db.executemany("INSERT OR REPLACE INTO history VALUES (?,?,?,?)",
                                   [(now,name,v["rx"],v["tx"]) for name,v in interface_rates.items()])
                    db.execute("DELETE FROM history WHERE ts < ?", (now-86400,))
                last_store = now
            old_sockets, old_ifaces, last = sockets, ifaces, start
        except Exception as exc:
            with LOCK: STATE["error"] = str(exc)
        time.sleep(max(0.1, 1-(time.monotonic()-start)))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            with LOCK: payload = json.dumps(STATE).encode()
            return self.send_payload(payload, "application/json; charset=utf-8")
        if parsed.path == "/api/history":
            q = parse_qs(parsed.query)
            iface = q.get("interface", [""])[0][:128]
            seconds = min(86400, max(60, int(q.get("seconds", ["60"])[0])))
            with sqlite3.connect(DB, timeout=5) as db:
                rows = db.execute("SELECT ts,rx,tx FROM history WHERE iface=? AND ts>=? ORDER BY ts",
                                  (iface, int(time.time())-seconds)).fetchall()
            # limit large responses to 1200 evenly spaced points
            stride = max(1, (len(rows)+1199)//1200)
            payload = json.dumps([{"ts":r[0],"rx":r[1],"tx":r[2]} for r in rows[::stride]]).encode()
            return self.send_payload(payload, "application/json; charset=utf-8")
        path = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        if path not in ("index.html", "app.js", "style.css"):
            self.send_error(404); return
        mime = {"index.html":"text/html", "app.js":"text/javascript", "style.css":"text/css"}[path]
        return self.send_payload((STATIC/path).read_bytes(), mime+"; charset=utf-8")
    def send_payload(self, data, mime):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    setup_db()
    threading.Thread(target=sampler, daemon=True).start()
    print(f"Simple TrueNAS Network Monitor v{VERSION} on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
