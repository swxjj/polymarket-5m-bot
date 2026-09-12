#!/usr/bin/env python3
"""
Polymarket 5-Minute BTC Momentum Paper Trading Engine & Real-Time Dashboard
----------------------------------------------------------------------------
Real-time forward Out-Of-Sample (OOS) simulator and live web dashboard
for the strategy in Novals83/5min-btc-polymarket.

Requires NO private keys, NO API credentials, and NO third-party packages.

Features:
- Polls live Polymarket Gamma API and CLOB order books for recurring 'btc-updown-5m-*' markets.
- Virtual order execution at real Top-of-Book Asks (accounting for real spread).
- Real-time stop-loss tracking and 20s time-exit at real Top-of-Book Bids.
- Embedded HTTP web server and REST API on port 8055 serving a sleek dark-mode cockpit.
- Real-time capital tracking (starting equity, cash, floating unrealized PnL, equity curve).
- Stores all interval quotes, fills, and resolutions in SQLite for persistence and auditability.
"""

import argparse
import datetime as dt
import http.server
import json
import logging
import os
import socketserver
import sqlite3
import sys
import threading
import time
import socket
import urllib.request
from pathlib import Path
from typing import Any, Optional

# Fallback DNS resolution for Polymarket in environments where ISP DNS filters or fails
_orig_getaddrinfo = socket.getaddrinfo
def _polymarket_dns_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and ('polymarket.com' in host):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('104.18.34.205', port))]
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if isinstance(host, str) and ('polymarket' in host):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('104.18.34.205', port))]
        raise
socket.getaddrinfo = _polymarket_dns_getaddrinfo


UTC = dt.timezone.utc

def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)

def ts_iso() -> str:
    return now_utc().isoformat().replace('+00:00', 'Z')

def bucket_5m(ts: int) -> int:
    return ts - (ts % 300)

def http_get_json(url: str, timeout: float = 8.0) -> Optional[Any]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PolymarketPaperTester/2.0',
        'Accept': 'application/json',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logging.debug("GET %s failed: %s", url, e)
    return None

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_schema(self):
        with self.get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_slug TEXT UNIQUE,
                    market_title TEXT,
                    start_ts INTEGER,
                    end_ts INTEGER,
                    side TEXT,
                    token_id TEXT,
                    entry_time TEXT,
                    seconds_left_at_entry REAL,
                    entry_ask REAL,
                    entry_bid REAL,
                    spread_at_entry REAL,
                    stake_usd REAL,
                    shares REAL,
                    stop_loss_price REAL,
                    exit_reason TEXT,
                    exit_time TEXT,
                    seconds_left_at_exit REAL,
                    exit_bid REAL,
                    scalp_pnl_usd REAL,
                    scalp_pnl_pct REAL,
                    resolved_winner TEXT,
                    settled_pnl_usd REAL,
                    status TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS quote_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_slug TEXT,
                    ts TEXT,
                    seconds_left REAL,
                    up_bid REAL,
                    up_ask REAL,
                    down_bid REAL,
                    down_ask REAL
                )
            ''')

    def save_trade(self, trade: dict[str, Any]):
        fields = [
            'market_slug', 'market_title', 'start_ts', 'end_ts', 'side', 'token_id',
            'entry_time', 'seconds_left_at_entry', 'entry_ask', 'entry_bid', 'spread_at_entry',
            'stake_usd', 'shares', 'stop_loss_price', 'exit_reason', 'exit_time',
            'seconds_left_at_exit', 'exit_bid', 'scalp_pnl_usd', 'scalp_pnl_pct',
            'resolved_winner', 'settled_pnl_usd', 'status'
        ]
        placeholders = ', '.join(['?'] * len(fields))
        cols = ', '.join(fields)
        updates = ', '.join([f"{f}=excluded.{f}" for f in fields])
        values = [trade.get(f) for f in fields]
        sql = f'''
            INSERT INTO trades ({cols}) VALUES ({placeholders})
            ON CONFLICT(market_slug) DO UPDATE SET {updates}
        '''
        with self.get_conn() as conn:
            conn.execute(sql, values)

    def get_recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def log_quote(self, market_slug: str, seconds_left: float, up_bid, up_ask, dn_bid, dn_ask):
        with self.get_conn() as conn:
            conn.execute('''
                INSERT INTO quote_ticks (market_slug, ts, seconds_left, up_bid, up_ask, down_bid, down_ask)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (market_slug, ts_iso(), seconds_left, up_bid, up_ask, dn_bid, dn_ask))

def compute_vwap_ask(asks: list[dict], target_shares: float) -> tuple[Optional[float], float]:
    """Computes volume-weighted average price (VWAP) for buying target_shares from asks."""
    if not asks:
        return None, 0.0
    sorted_asks = sorted(
        [{'price': float(x['price']), 'size': float(x['size'])} for x in asks if 'price' in x and 'size' in x],
        key=lambda x: x['price']
    )
    if not sorted_asks:
        return None, 0.0
    needed = target_shares
    total_cost = 0.0
    filled = 0.0
    for level in sorted_asks:
        p = level['price']
        s = level['size']
        take = min(needed, s)
        total_cost += take * p
        filled += take
        needed -= take
        if needed <= 0:
            break
    if filled == 0:
        return None, 0.0
    return round(total_cost / filled, 4), round(filled, 4)

def compute_vwap_bid(bids: list[dict], target_shares: float) -> tuple[Optional[float], float]:
    """Computes volume-weighted average price (VWAP) for selling target_shares to bids."""
    if not bids:
        return None, 0.0
    sorted_bids = sorted(
        [{'price': float(x['price']), 'size': float(x['size'])} for x in bids if 'price' in x and 'size' in x],
        key=lambda x: x['price'],
        reverse=True
    )
    if not sorted_bids:
        return None, 0.0
    needed = target_shares
    total_revenue = 0.0
    filled = 0.0
    for level in sorted_bids:
        p = level['price']
        s = level['size']
        take = min(needed, s)
        total_revenue += take * p
        filled += take
        needed -= take
        if needed <= 0:
            break
    if filled == 0:
        return None, 0.0
    return round(total_revenue / filled, 4), round(filled, 4)

class PolymarketClient:
    GAMMA_BASE = "https://gamma-api.polymarket.com"
    CLOB_BASE = "https://clob.polymarket.com"

    @classmethod
    def get_event(cls, slug: str) -> Optional[dict[str, Any]]:
        url = f"{cls.GAMMA_BASE}/events?slug={slug}"
        data = http_get_json(url)
        return data[0] if (data and isinstance(data, list)) else None

    @classmethod
    def get_order_book(cls, token_id: str) -> tuple[Optional[float], Optional[float]]:
        """Returns (best_bid, best_ask) for the token."""
        details = cls.get_order_book_details(token_id)
        return details.get('best_bid'), details.get('best_ask')

    @classmethod
    def get_order_book_details(cls, token_id: str) -> dict[str, Any]:
        """Returns full order book details including best quotes and raw bids/asks."""
        url = f"{cls.CLOB_BASE}/book?token_id={token_id}"
        data = http_get_json(url)
        if not data:
            return {'best_bid': None, 'best_ask': None, 'bids': [], 'asks': []}
        bids_raw = data.get('bids', [])
        asks_raw = data.get('asks', [])
        bids = [float(x['price']) for x in bids_raw if 'price' in x]
        asks = [float(x['price']) for x in asks_raw if 'price' in x]
        best_bid = max(bids) if bids else None
        best_ask = min(asks) if asks else None
        return {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'bids': bids_raw,
            'asks': asks_raw
        }

class PaperTrader:
    def __init__(self, config: dict[str, Any]):
        self.cfg = config
        self.db = Database(config['db_path'])
        self.lock = threading.Lock()
        
        # Capital State
        self.starting_capital = float(config.get('start_capital', 100.0))
        self.cash = self.starting_capital
        self.equity_history = [self.starting_capital]

        # Active Session State
        self.active_trade: Optional[dict[str, Any]] = None
        self.current_slug: Optional[str] = None
        self.latest_market_info: dict[str, Any] = {}

    def get_status_payload(self) -> dict[str, Any]:
        with self.lock:
            # Calculate floating unrealized PnL
            unrealized_pnl = 0.0
            unrealized_pct = 0.0
            pos_dict = None
            if self.active_trade:
                tr = dict(self.active_trade)
                cur_bid = tr.get('current_bid') or tr.get('entry_ask')
                pos_val = tr['shares'] * cur_bid
                unrealized_pnl = round(pos_val - tr['stake_usd'], 4)
                unrealized_pct = round((unrealized_pnl / tr['stake_usd']) * 100, 2)
                tr['unrealized_pnl_usd'] = unrealized_pnl
                tr['unrealized_pnl_pct'] = unrealized_pct
                pos_dict = tr

            current_equity = round(self.cash + (self.active_trade['shares'] * (self.active_trade.get('current_bid') or self.active_trade['entry_ask']) if self.active_trade else 0.0), 4)

            trades = self.db.get_recent_trades(limit=50)

            # Performance stats
            total_trades = len(trades)
            scalp_wins = [t for t in trades if t['scalp_pnl_usd'] is not None and t['scalp_pnl_usd'] > 0]
            scalp_losses = [t for t in trades if t['scalp_pnl_usd'] is not None and t['scalp_pnl_usd'] <= 0]
            total_scalp_pnl = sum([t['scalp_pnl_usd'] for t in trades if t['scalp_pnl_usd'] is not None])

            settled_trades = [t for t in trades if t['settled_pnl_usd'] is not None]
            settled_wins = [t for t in settled_trades if t['settled_pnl_usd'] > 0]
            total_settled_pnl = sum([t['settled_pnl_usd'] for t in settled_trades])

            avg_spread = sum([t['spread_at_entry'] or 0 for t in trades]) / total_trades if total_trades else 0.0

            stats = {
                'total_trades': total_trades,
                'scalp_wins': len(scalp_wins),
                'scalp_losses': len(scalp_losses),
                'scalp_win_rate_pct': round((len(scalp_wins) / total_trades * 100), 1) if total_trades else 0.0,
                'total_scalp_pnl': round(total_scalp_pnl, 4),
                'settled_trades': len(settled_trades),
                'settled_wins': len(settled_wins),
                'settled_win_rate_pct': round((len(settled_wins) / len(settled_trades) * 100), 1) if settled_trades else 0.0,
                'total_settled_pnl': round(total_settled_pnl, 4),
                'avg_spread_paid': round(avg_spread, 4),
            }

            capital_info = {
                'starting_capital': self.starting_capital,
                'available_cash': round(self.cash, 4),
                'current_equity': current_equity,
                'equity_history': list(self.equity_history[-60:]),
            }

            return {
                'server_time': ts_iso(),
                'capital': capital_info,
                'active_market': self.latest_market_info,
                'active_position': pos_dict,
                'stats': stats,
                'recent_trades': trades,
                'config': {
                    'threshold': self.cfg['threshold'],
                    'max_entry_ask': self.cfg.get('max_entry_ask', 0.88),
                    'stake_usd': self.cfg['stake_usd'],
                    'stop_loss_pct': self.cfg['stop_loss_pct'],
                    'exit_before_sec': self.cfg['exit_before_sec'],
                    'sim_latency_ms': self.cfg.get('sim_latency_ms', 300),
                    'sl_slippage_cents': self.cfg.get('sl_slippage_cents', 0.015),
                }
            }

    def run_loop(self):
        logging.info("=" * 65)
        logging.info("Starting 5m BTC Momentum Paper Trader & Dashboard Engine (Realistic Mode)")
        logging.info("Capital: $%.2f | Entry Range: $%.2f - $%.2f | Stake: $%.2f",
                     self.starting_capital, self.cfg['threshold'], self.cfg.get('max_entry_ask', 0.88), self.cfg['stake_usd'])
        logging.info("Realistic Frictions: Latency=%dms | SL Slippage=-$%.3f | Depth Fill=VWAP",
                     self.cfg.get('sim_latency_ms', 300), self.cfg.get('sl_slippage_cents', 0.015))
        logging.info("Dashboard URL: http://localhost:%d", self.cfg['port'])
        logging.info("=" * 65)

        while True:
            try:
                self.tick()
            except Exception as e:
                logging.error("Tick error: %s", e, exc_info=True)
            time.sleep(self.cfg['poll_sec'])

    def tick(self):
        now = int(time.time())
        cur_bucket = bucket_5m(now)
        slug = f"btc-updown-5m-{cur_bucket}"

        # If we crossed into a new 5m bucket, check settlements of past contracts
        if slug != self.current_slug:
            self.current_slug = slug
            self.check_unsettled_trades()

        event = PolymarketClient.get_event(slug)
        if not event:
            logging.debug("Waiting for market creation for slug: %s", slug)
            return

        markets = event.get('markets') or []
        if not markets:
            return
        mkt = markets[0]

        # Parse end date and seconds remaining
        end_iso = mkt.get('endDate') or mkt.get('endDateIso') or ''
        try:
            end_ts = dt.datetime.fromisoformat(end_iso.replace('Z', '+00:00')).timestamp()
            seconds_left = end_ts - time.time()
        except Exception:
            seconds_left = max(0, (cur_bucket + 300) - time.time())

        # Extract outcomes and token IDs
        outcomes_raw = mkt.get('outcomes')
        outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])
        tokens_raw = mkt.get('clobTokenIds')
        tokens = json.loads(tokens_raw) if isinstance(tokens_raw, str) else (tokens_raw or [])

        if len(tokens) < 2 or len(outcomes) < 2:
            return

        # Map UP/DOWN
        up_idx = 0 if 'up' in outcomes[0].lower() else 1
        dn_idx = 1 - up_idx
        up_token, dn_token = tokens[up_idx], tokens[dn_idx]

        # Fetch CLOB Top-of-Book
        up_bid, up_ask = PolymarketClient.get_order_book(up_token)
        dn_bid, dn_ask = PolymarketClient.get_order_book(dn_token)

        self.db.log_quote(slug, seconds_left, up_bid, up_ask, dn_bid, dn_ask)

        with self.lock:
            self.latest_market_info = {
                'slug': slug,
                'title': event.get('title', slug),
                'seconds_left': max(0.0, round(seconds_left, 1)),
                'up_bid': up_bid,
                'up_ask': up_ask,
                'down_bid': dn_bid,
                'down_ask': dn_ask,
                'up_token': up_token,
                'down_token': dn_token,
            }

            # Update live quote on active position if open
            if self.active_trade and self.active_trade['market_slug'] == slug:
                self.active_trade['current_bid'] = up_bid if self.active_trade['side'] == 'UP' else dn_bid
                cur_bid = self.active_trade['current_bid'] or self.active_trade['entry_ask']
                pos_val = self.active_trade['shares'] * cur_bid
                unrealized = pos_val - self.active_trade['stake_usd']
                cur_eq = round(self.cash + pos_val, 4)
                self.equity_history.append(cur_eq)
                if len(self.equity_history) > 120:
                    self.equity_history.pop(0)

        # 1. Manage Open Position
        if self.active_trade and self.active_trade['market_slug'] == slug:
            self.manage_open_position(seconds_left, up_bid, up_ask, dn_bid, dn_ask)
            return

        # 2. Check Entry Rules
        # Must be in window (e.g. 150s down to 60s)
        max_entry = self.cfg.get('max_entry_seconds_left', 150)
        min_entry = self.cfg.get('min_entry_seconds_left', 60)
        if seconds_left > max_entry:
            return
        if seconds_left < min_entry:
            return

        # Momentum Trigger: Check if either side ask within [threshold, max_entry_ask]
        max_entry_ask = self.cfg.get('max_entry_ask', 0.88)
        min_threshold = self.cfg['threshold']

        candidates = []
        if up_ask is not None and min_threshold <= up_ask <= max_entry_ask:
            candidates.append(('UP', up_ask, up_bid, up_token))
        elif up_ask is not None and up_ask > max_entry_ask:
            logging.debug("Skipping UP on %s: Ask $%.2f exceeds ceiling $%.2f", slug, up_ask, max_entry_ask)

        if dn_ask is not None and min_threshold <= dn_ask <= max_entry_ask:
            candidates.append(('DOWN', dn_ask, dn_bid, dn_token))
        elif dn_ask is not None and dn_ask > max_entry_ask:
            logging.debug("Skipping DOWN on %s: Ask $%.2f exceeds ceiling $%.2f", slug, dn_ask, max_entry_ask)

        if not candidates:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        picked_side, best_ask, best_bid, picked_token = candidates[0]

        # Sizing check against cash
        stake = min(self.cfg['stake_usd'], self.cash)
        if stake < 1.0:
            logging.warning("Insufficient cash to open position: $%.2f", self.cash)
            return

        self.open_paper_trade(
            slug=slug,
            title=event.get('title', slug),
            start_ts=cur_bucket,
            end_ts=cur_bucket + 300,
            side=picked_side,
            token_id=picked_token,
            ask_price=best_ask,
            bid_price=best_bid,
            seconds_left=seconds_left,
            stake=stake
        )

    def open_paper_trade(self, slug, title, start_ts, end_ts, side, token_id, ask_price, bid_price, seconds_left, stake):
        # 1. Realistic Latency Simulation (EIP-712 signing + network roundtrip)
        sim_latency_ms = self.cfg.get('sim_latency_ms', 300)
        book = None
        if sim_latency_ms > 0:
            logging.info("[REALISTIC LATENCY] Simulating EIP-712 order signing + network roundtrip (%d ms)...", sim_latency_ms)
            time.sleep(sim_latency_ms / 1000.0)
            book = PolymarketClient.get_order_book_details(token_id)
            latest_ask = book.get('best_ask')
            latest_bid = book.get('best_bid')
            if latest_ask is None:
                logging.warning("[REJECT] Order cancelled: order book empty after signature latency")
                return
            max_allowed = self.cfg.get('max_entry_ask', 0.88) + 0.02
            if latest_ask > max_allowed:
                logging.warning("[SLIPPAGE REJECT] Ask surged from $%.2f to $%.2f (exceeds cap + tolerance). Cancelling.", ask_price, latest_ask)
                return
            ask_price = latest_ask
            bid_price = latest_bid or bid_price
        else:
            book = PolymarketClient.get_order_book_details(token_id)

        # 2. Realistic Depth Fill: compute VWAP for target shares
        target_shares = stake / ask_price
        vwap_ask, avail_shares = compute_vwap_ask(book.get('asks', []), target_shares)
        if vwap_ask is not None and vwap_ask > ask_price:
            logging.info("[DEPTH SLIPPAGE] Top ask $%.2f slipped to VWAP $%.4f for %.2f shares", ask_price, vwap_ask, target_shares)
            ask_price = vwap_ask

        shares = stake / ask_price
        sl_price = round(ask_price * (1.0 - self.cfg['stop_loss_pct']), 4)
        spread = round((ask_price - (bid_price or ask_price)), 4)

        trade = {
            'market_slug': slug,
            'market_title': title,
            'start_ts': start_ts,
            'end_ts': end_ts,
            'side': side,
            'token_id': token_id,
            'entry_time': ts_iso(),
            'seconds_left_at_entry': round(seconds_left, 1),
            'entry_ask': ask_price,
            'entry_bid': bid_price,
            'spread_at_entry': spread,
            'stake_usd': stake,
            'shares': round(shares, 4),
            'stop_loss_price': sl_price,
            'current_bid': bid_price,
            'exit_reason': None,
            'exit_time': None,
            'seconds_left_at_exit': None,
            'exit_bid': None,
            'scalp_pnl_usd': None,
            'scalp_pnl_pct': None,
            'resolved_winner': None,
            'settled_pnl_usd': None,
            'status': 'OPEN'
        }

        with self.lock:
            self.cash -= stake
            self.active_trade = trade
            self.db.save_trade(trade)

        logging.info(">>> [ENTRY] Bought %s on %s at Ask $%.2f (Bid: $%.2f, Spread: $%.2f) | Shares: %.2f | SL: $%.3f (at %.1fs left)",
                     side, slug, ask_price, bid_price or 0, spread, shares, sl_price, seconds_left)

    def manage_open_position(self, seconds_left, up_bid, up_ask, dn_bid, dn_ask):
        tr = self.active_trade
        if not tr:
            return

        current_bid = up_bid if tr['side'] == 'UP' else dn_bid
        if current_bid is None:
            return

        # Check Stop-Loss with adverse gap slippage
        if current_bid <= tr['stop_loss_price']:
            sl_slippage = self.cfg.get('sl_slippage_cents', 0.015)
            effective_bid = max(0.01, round(current_bid - sl_slippage, 4))
            logging.warning("[STOP LOSS SLIPPAGE] Triggered at $%.2f. Executed at $%.4f with -$%.3f adverse gap",
                            current_bid, effective_bid, sl_slippage)
            self.close_position(
                reason=f"STOP_LOSS_{int(self.cfg['stop_loss_pct'] * 100)}PCT",
                exit_bid=effective_bid,
                seconds_left=seconds_left
            )
            return

        # Check Time-Based Scalp Exit (e.g. 20s before expiry) with depth fill VWAP
        if seconds_left <= self.cfg['exit_before_sec']:
            book = PolymarketClient.get_order_book_details(tr['token_id'])
            vwap_bid, avail_shares = compute_vwap_bid(book.get('bids', []), tr['shares'])
            effective_bid = vwap_bid if vwap_bid is not None else current_bid
            if vwap_bid is not None and vwap_bid < current_bid:
                logging.info("[EXIT DEPTH SLIPPAGE] Top bid $%.2f slipped to VWAP $%.4f for %.2f shares",
                             current_bid, vwap_bid, tr['shares'])
            self.close_position(
                reason=f"TIME_EXIT_{self.cfg['exit_before_sec']}S_BEFORE_CLOSE",
                exit_bid=effective_bid,
                seconds_left=seconds_left
            )
            return

    def close_position(self, reason: str, exit_bid: float, seconds_left: float):
        tr = self.active_trade
        if not tr:
            return

        proceeds = tr['shares'] * exit_bid
        pnl_usd = round(proceeds - tr['stake_usd'], 4)
        pnl_pct = round((pnl_usd / tr['stake_usd']) * 100, 2)

        tr['exit_reason'] = reason
        tr['exit_time'] = ts_iso()
        tr['seconds_left_at_exit'] = round(seconds_left, 1)
        tr['exit_bid'] = exit_bid
        tr['scalp_pnl_usd'] = pnl_usd
        tr['scalp_pnl_pct'] = pnl_pct
        tr['status'] = 'CLOSED'

        with self.lock:
            self.cash += proceeds
            new_eq = round(self.cash, 4)
            self.equity_history.append(new_eq)
            if len(self.equity_history) > 120:
                self.equity_history.pop(0)
            self.db.save_trade(tr)
            self.active_trade = None

        pnl_sign = "+" if pnl_usd >= 0 else ""
        logging.info("<<< [EXIT - %s] Closed %s on %s at Bid $%.2f | PnL: %s$%.2f (%s%.2f%%) (at %.1fs left)",
                     reason, tr['side'], tr['market_slug'], exit_bid, pnl_sign, pnl_usd, pnl_sign, pnl_pct, seconds_left)

    def check_unsettled_trades(self):
        """Checks past closed markets to record final resolution winner and Hold-To-Maturity PnL."""
        with self.db.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT market_slug, side, entry_ask, stake_usd, shares FROM trades WHERE resolved_winner IS NULL")
            rows = cursor.fetchall()

        for slug, side, entry_ask, stake, shares in rows:
            ev = PolymarketClient.get_event(slug)
            if not ev:
                continue
            mkts = ev.get('markets') or []
            if not mkts or not mkts[0].get('closed'):
                continue

            mkt = mkts[0]
            prices_raw = mkt.get('outcomePrices')
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else (prices_raw or [])
            outcomes_raw = mkt.get('outcomes')
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])

            if len(prices) >= 2 and len(outcomes) >= 2:
                winner = None
                if float(prices[0]) == 1.0:
                    winner = outcomes[0].upper()
                elif float(prices[1]) == 1.0:
                    winner = outcomes[1].upper()

                if winner:
                    settled_pnl = round(shares * 1.0 - stake, 4) if winner == side else round(-stake, 4)
                    with self.db.get_conn() as conn:
                        conn.execute(
                            "UPDATE trades SET resolved_winner = ?, settled_pnl_usd = ? WHERE market_slug = ?",
                            (winner, settled_pnl, slug)
                        )
                    logging.info("[SETTLEMENT] %s resolved to %s. (Hold-to-expiry PnL: %s$%.2f)",
                                 slug, winner, "+" if settled_pnl >= 0 else "", settled_pnl)

class DashboardHttpHandler(http.server.SimpleHTTPRequestHandler):
    trader_instance: Optional[PaperTrader] = None
    dashboard_dir: str = ""

    def translate_path(self, path):
        # Serve static assets from dashboard_dir
        rel = path.lstrip('/')
        if not rel or rel == 'index.html':
            return os.path.join(self.dashboard_dir, 'index.html')
        return os.path.join(self.dashboard_dir, rel)

    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            if self.trader_instance:
                payload = self.trader_instance.get_status_payload()
            else:
                payload = {'error': 'trader_uninitialized'}
            self.wfile.write(json.dumps(payload).encode('utf-8'))
            return

        # Serve static file
        super().do_GET()

    def log_message(self, format, *args):
        # Silence verbose GET request logging
        return

def run_server(trader: PaperTrader, dashboard_dir: str, port: int):
    DashboardHttpHandler.trader_instance = trader
    DashboardHttpHandler.dashboard_dir = dashboard_dir
    with socketserver.ThreadingTCPServer(('0.0.0.0', port), DashboardHttpHandler) as httpd:
        logging.info("Serving Live Web Dashboard on http://localhost:%d", port)
        httpd.serve_forever()

def print_stats(db_path: str):
    db = Database(db_path)
    trades = db.get_recent_trades(limit=500)
    if not trades:
        print(f"No trades found in database: {db_path}")
        return

    total = len(trades)
    scalp_wins = [t for t in trades if t['scalp_pnl_usd'] is not None and t['scalp_pnl_usd'] > 0]
    scalp_losses = [t for t in trades if t['scalp_pnl_usd'] is not None and t['scalp_pnl_usd'] <= 0]
    total_scalp_pnl = sum([t['scalp_pnl_usd'] for t in trades if t['scalp_pnl_usd'] is not None])

    settled_trades = [t for t in trades if t['settled_pnl_usd'] is not None]
    settled_wins = [t for t in settled_trades if t['settled_pnl_usd'] > 0]
    total_settled_pnl = sum([t['settled_pnl_usd'] for t in settled_trades])

    avg_spread = sum([t['spread_at_entry'] or 0 for t in trades]) / total if total else 0.0

    print("\n" + "=" * 65)
    print("      POLYMARKET 5M BTC MOMENTUM PAPER TRADING REPORT      ")
    print("=" * 65)
    print(f"Total Completed Sessions:     {total}")
    print(f"Average Entry Spread Paid:    ${avg_spread:.4f}")
    print("-" * 65)
    print("STRATEGY A: ACTIVE SCALP (Exit 20s before close)")
    print(f"  Win / Loss:                 {len(scalp_wins)}W / {len(scalp_losses)}L")
    print(f"  Win Rate:                   {(len(scalp_wins)/total*100):.1f}%")
    print(f"  Total Realized PnL:         {'+' if total_scalp_pnl >= 0 else ''}${total_scalp_pnl:.2f}")
    print("-" * 65)
    print("STRATEGY B: HOLD TO SETTLEMENT ($1 or $0)")
    print(f"  Settled Samples:            {len(settled_trades)}")
    print(f"  Win / Loss:                 {len(settled_wins)}W / {len(settled_trades) - len(settled_wins)}L")
    print(f"  Win Rate:                   {(len(settled_wins)/len(settled_trades)*100):.1f}%" if settled_trades else "  N/A")
    print(f"  Total Settled PnL:          {'+' if total_settled_pnl >= 0 else ''}${total_settled_pnl:.2f}")
    print("=" * 65 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Polymarket 5m BTC Momentum Paper Trader & Dashboard")
    parser.add_argument("--threshold", type=float, default=0.70, help="Entry ask price threshold minimum (default: 0.70)")
    parser.add_argument("--max-entry-ask", type=float, default=0.88, help="Maximum entry ask price cap (default: 0.88)")
    parser.add_argument("--stake-usd", type=float, default=5.0, help="Notional stake per trade in USD (default: 5.0)")
    parser.add_argument("--start-capital", type=float, default=100.0, help="Initial portfolio capital in USD (default: 100.0)")
    parser.add_argument("--stop-loss-pct", type=float, default=0.25, help="Stop loss percentage from entry (default: 0.25)")
    parser.add_argument("--sl-slippage-cents", type=float, default=0.015, help="Adverse slippage penalty on stop loss in USD (default: 0.015)")
    parser.add_argument("--sim-latency-ms", type=int, default=300, help="Simulated EIP-712 signing & network latency in ms (default: 300)")
    parser.add_argument("--exit-before-sec", type=int, default=20, help="Exit N seconds before close (default: 20)")
    parser.add_argument("--max-entry-seconds-left", type=int, default=150, help="Earliest entry window (default: 150s)")
    parser.add_argument("--min-entry-seconds-left", type=int, default=60, help="Latest entry window (default: 60s)")
    parser.add_argument("--poll-sec", type=float, default=1.5, help="Polling interval in seconds (default: 1.5)")
    parser.add_argument("--port", type=int, default=8055, help="Dashboard web server port (default: 8055)")
    parser.add_argument("--db-path", default="paper_trades.db", help="SQLite database path (default: paper_trades.db)")
    parser.add_argument("--report", action="store_true", help="Print summary report of trades from database and exit")
    parser.add_argument("--verbose", action="store_true", help="Verbose debug logging")

    args = parser.parse_args()

    if args.report:
        print_stats(args.db_path)
        return

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    dashboard_dir = str(Path(__file__).resolve().parent.parent / "dashboard")
    trader = PaperTrader(vars(args))

    # Start HTTP server in a separate background daemon thread
    server_thread = threading.Thread(
        target=run_server,
        args=(trader, dashboard_dir, args.port),
        daemon=True
    )
    server_thread.start()

    # Run trading loop in main thread
    trader.run_loop()

if __name__ == "__main__":
    main()

