#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import threading
import urllib.request
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON_EXE = r'C:\Users\flia.barros\AppData\Local\Programs\Python\Python311\python.exe'
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

NTFY_TOPIC = 'agy_160911notis'
URL_FILE = BASE_DIR / 'poly_tunnel_url.txt'

def send_ntfy(message: str, title: str = 'Polymarket 5m Dual Engines', click_url: str = None):
    for domain in ['https://ntfy.sh', 'https://ntgy.sh']:
        try:
            headers = {
                'Title': title,
                'Priority': 'high',
                'Tags': 'chart_with_upwards_trend,rocket,robot'
            }
            if click_url:
                headers['Click'] = click_url
            req = urllib.request.Request(
                f'{domain}/{NTFY_TOPIC}',
                data=message.encode('utf-8'),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    print(f'[NTFY] Notification sent successfully to {domain}/{NTFY_TOPIC}', flush=True)
                    return
        except Exception as e:
            print(f'[NTFY] Error sending notification to {domain}: {e}', flush=True)

def expose_gateway_service(port: int, alias: str, name: str, set_primary: bool = False):
    for attempt in range(6):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8899/_api/expose",
                data=json.dumps({
                    "port": port,
                    "alias": alias,
                    "name": name,
                    "set_primary": set_primary
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print(f"[GATEWAY] Successfully registered port {port} ({alias}) in ControlRemoto Gateway", flush=True)
                    return True
        except Exception:
            time.sleep(1.5)
    return False

def start_engine(cmd: list[str], prefix: str):
    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    def log_stream():
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(f'{prefix} {line.strip()}', flush=True)

    threading.Thread(target=log_stream, daemon=True).start()
    return proc

def run():
    print('=' * 70, flush=True)
    print('  POLYMARKET 5M PARALLEL ENGINES & GATEWAY SUPERVISOR', flush=True)
    print('=' * 70, flush=True)

    bot_script = BASE_DIR / 'scripts' / 'polymarket_5m_paper_tester.py'

    # Engine 1: With BTC spot check (>= $60 move) on port 8055
    cmd_btc = [
        PYTHON_EXE, str(bot_script),
        '--port', '8055',
        '--db-path', 'paper_trades.db',
        '--min-btc-move', '60.0',
        '--verbose'
    ]

    # Engine 2: Pure Momentum (no BTC move check) on port 8056
    cmd_pure = [
        PYTHON_EXE, str(bot_script),
        '--port', '8056',
        '--db-path', 'paper_trades_pure.db',
        '--no-require-btc-move',
        '--verbose'
    ]

    print(f'[INFO] Starting Engine 1 (With BTC Check >= $60) on port 8055...', flush=True)
    proc_btc = start_engine(cmd_btc, '[BTC-8055]')

    print(f'[INFO] Starting Engine 2 (Pure Momentum - No BTC Check) on port 8056...', flush=True)
    proc_pure = start_engine(cmd_pure, '[PURE-8056]')

    time.sleep(3.0)

    # Register both ports with Gateway
    expose_gateway_service(8055, "poly", "Polymarket 5m Cockpit (BTC Check)", set_primary=True)
    expose_gateway_service(8056, "pure", "Polymarket 5m (Pure Momentum)", set_primary=False)

    domain_url = "https://controlremoto.tech"
    poly_subdomain = "https://poly.controlremoto.tech"
    pure_subdomain = "https://pure.controlremoto.tech"

    print(f'\n=======================================================', flush=True)
    print(f'  PRIMARY DASHBOARD (BTC CHECK)   : {domain_url}', flush=True)
    print(f'  SUBDOMAIN (BTC CHECK)           : {poly_subdomain}', flush=True)
    print(f'  SUBDOMAIN (PURE MOMENTUM)       : {pure_subdomain}', flush=True)
    print(f'=======================================================\n', flush=True)

    with open(URL_FILE, 'w', encoding='utf-8') as f:
        f.write(f"{domain_url}\n{poly_subdomain}\n{pure_subdomain}\n")

    msg = (
        f"🚀 Polymarket 5m Dual Engines ONLINE\n\n"
        f"1️⃣ With BTC Check (>= $60):\n{poly_subdomain} (or {domain_url})\n\n"
        f"2️⃣ Pure Momentum (No BTC Check):\n{pure_subdomain}\n\n"
        f"Both engines running forward paper testing on live CLOB order books."
    )
    send_ntfy(msg, title='Polymarket Dual Engines LIVE', click_url=domain_url)

    try:
        while True:
            time.sleep(3.0)

            # Auto-restart Engine 1 if exited
            if proc_btc.poll() is not None:
                print(f'[WARN] Engine 1 (BTC Check) exited with code {proc_btc.poll()}. Restarting in 2s...', flush=True)
                time.sleep(2.0)
                proc_btc = start_engine(cmd_btc, '[BTC-8055]')

            # Auto-restart Engine 2 if exited
            if proc_pure.poll() is not None:
                print(f'[WARN] Engine 2 (Pure Momentum) exited with code {proc_pure.poll()}. Restarting in 2s...', flush=True)
                time.sleep(2.0)
                proc_pure = start_engine(cmd_pure, '[PURE-8056]')

    except KeyboardInterrupt:
        print('\n[INFO] Shutting down parallel engines supervisor...', flush=True)
    finally:
        for p, name in [(proc_btc, 'Engine 1'), (proc_pure, 'Engine 2')]:
            try:
                p.terminate()
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print('[INFO] All engine processes stopped.', flush=True)

if __name__ == '__main__':
    run()
