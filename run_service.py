#!/usr/bin/env python3
import os
import re
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

CLOUDFLARED_EXE = r'C:\Users\flia.barros\.gemini\remote-control\cloudflared.exe'
NTFY_TOPIC = 'agy_160911notis'
URL_FILE = BASE_DIR / 'poly_tunnel_url.txt'
REMOTE_POLY_FILE = Path(r'C:\Users\flia.barros\.gemini\remote-control\poly_url.txt')

def send_ntfy(message: str, title: str = 'Polymarket 5m Cockpit', click_url: str = None):
    for domain in ['https://ntfy.sh', 'https://ntgy.sh']:
        try:
            headers = {
                'Title': title,
                'Priority': 'high',
                'Tags': 'chart_with_upwards_trend,rocket,bitcoin'
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
            print(f'[NTFY] Error sending to {domain}: {e}', flush=True)

def run():
    print('=' * 65, flush=True)
    print('  POLYMARKET 5M BTC MOMENTUM PAPER TRADER & TUNNEL SUPERVISOR', flush=True)
    print('=' * 65, flush=True)

    bot_script = BASE_DIR / 'scripts' / 'polymarket_5m_paper_tester.py'
    print(f'[INFO] Starting Paper Trader Engine: {bot_script}', flush=True)
    
    bot_proc = subprocess.Popen(
        [PYTHON_EXE, str(bot_script), '--verbose'],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    def log_bot_output():
        for line in iter(bot_proc.stdout.readline, ''):
            if line:
                print(f'[BOT] {line.strip()}', flush=True)

    threading.Thread(target=log_bot_output, daemon=True).start()
    time.sleep(2.5)

    domain_url = "https://controlremoto.tech"
    poly_subdomain = "https://poly.controlremoto.tech"
    print(f'\n=======================================================', flush=True)
    print(f'  LIVE POLYMARKET DASHBOARD URL: {domain_url}', flush=True)
    print(f'  SUBDOMAIN URL                 : {poly_subdomain}', flush=True)
    print(f'=======================================================\n', flush=True)
    
    with open(URL_FILE, 'w', encoding='utf-8') as f:
        f.write(domain_url)

    # Ensure Gateway is exposed for port 8055
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8899/_api/expose",
                data=json.dumps({"port": 8055, "alias": "poly", "name": "Polymarket 5m Cockpit", "set_primary": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print("[INFO] Port 8055 successfully registered in ControlRemoto Gateway", flush=True)
                    break
        except Exception:
            time.sleep(1.0)

    msg = (
        f"📊 Polymarket 5m BTC Cockpit LIVE\n\n"
        f"Dashboard en vivo:\n{domain_url}\n\n"
        f"Subdomain:\n{poly_subdomain}\n\n"
        f"Paper trading en vivo sobre el libro CLOB."
    )
    send_ntfy(msg, title='Polymarket 5m Live Dashboard', click_url=domain_url)

    cf_proc = None

    try:
        while True:
            time.sleep(2.0)
            if bot_proc.poll() is not None:
                print(f'[ERROR] Bot process terminated with code {bot_proc.poll()}', flush=True)
                break
            if cf_proc and cf_proc.poll() is not None:
                print(f'[ERROR] Cloudflared process terminated with code {cf_proc.poll()}', flush=True)
                break
    except KeyboardInterrupt:
        print('[INFO] Shutting down supervisor...', flush=True)
    finally:
        try:
            bot_proc.terminate()
        except Exception:
            pass
        if cf_proc:
            try:
                cf_proc.terminate()
            except Exception:
                pass

if __name__ == '__main__':
    run()
