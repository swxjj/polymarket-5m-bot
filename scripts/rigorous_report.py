#!/usr/bin/env python3
"""
Rigorous Statistical Report for Live Polymarket Engines
------------------------------------------------------
Exclusively analyzes current contemporary forward runs:
1. Engine 1: With BTC Check (paper_trades.db)
2. Engine 2: Pure Momentum (paper_trades_pure.db)

Calculates 95% Wilson confidence intervals, paired hypothesis tests,
drawdowns, and sample size progress.
"""

import sqlite3
import math
import argparse
from pathlib import Path
import numpy as np
import scipy.stats as stats

BASE_DIR = Path(__file__).resolve().parent.parent

def wilson_ci(k: int, n: int, confidence: float = 0.95) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    z = stats.norm.ppf((1 + confidence) / 2)
    p_hat = k / n
    denom = 1 + (z**2) / n
    center = (p_hat + (z**2) / (2 * n)) / denom
    margin = (z * math.sqrt((p_hat * (1 - p_hat) / n) + ((z**2) / (4 * n**2)))) / denom
    return p_hat, max(0.0, center - margin), min(1.0, center + margin)

def analyze_engine_db(db_path: Path):
    if not db_path.exists():
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM trades WHERE status != 'EXCLUDED_ANOMALY' ORDER BY id ASC")
    trades = [dict(r) for r in c.fetchall()]
    n = len(trades)
    if n == 0:
        return None

    c.execute("SELECT COUNT(*) FROM trades WHERE status = 'EXCLUDED_ANOMALY'")
    excluded_anomalies = c.fetchone()[0]

    # Scalp stats
    completed = [t for t in trades if t['scalp_pnl_usd'] is not None]
    n_comp = len(completed)
    scalp_wins = sum(1 for t in completed if t['scalp_pnl_usd'] > 0)
    scalp_pnl_vals = [t['scalp_pnl_usd'] for t in completed]
    scalp_wr, scalp_wr_low, scalp_wr_high = wilson_ci(scalp_wins, n_comp)

    # Settled stats
    settled = [t for t in completed if t['settled_pnl_usd'] is not None]
    n_settled = len(settled)
    settled_wins = sum(1 for t in settled if t['settled_pnl_usd'] > 0)
    settled_pnl_vals = [t['settled_pnl_usd'] for t in settled]
    settled_wr, settled_wr_low, settled_wr_high = wilson_ci(settled_wins, n_settled)

    # Paired differences (Hold vs Scalp)
    diffs = [t['settled_pnl_usd'] - t['scalp_pnl_usd'] for t in settled]
    mean_diff = np.mean(diffs) if diffs else 0.0
    std_diff = np.std(diffs, ddof=1) if len(diffs) > 1 else 0.0
    se_diff = std_diff / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
    t_stat = mean_diff / se_diff if se_diff > 0 else 0.0
    p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=len(diffs)-1)) if len(diffs) > 1 else 1.0

    # Capital & Drawdown
    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    max_dd_pct = 0.0
    for pnl in scalp_pnl_vals:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        dd_pct = (dd / peak) * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct

    # Exit reasons
    c.execute("SELECT exit_reason, COUNT(*), SUM(scalp_pnl_usd) FROM trades WHERE scalp_pnl_usd IS NOT NULL AND status != 'EXCLUDED_ANOMALY' GROUP BY exit_reason")
    reasons = {r[0]: {'count': r[1], 'pnl': round(r[2] or 0.0, 2)} for r in c.fetchall()}

    # Price buckets
    c.execute("""
        SELECT 
            CASE 
                WHEN entry_ask < 0.75 THEN '0.70-0.74'
                WHEN entry_ask < 0.80 THEN '0.75-0.79'
                WHEN entry_ask < 0.85 THEN '0.80-0.84'
                ELSE '0.85-0.88'
            END as bucket,
            COUNT(*),
            SUM(CASE WHEN scalp_pnl_usd > 0 THEN 1 ELSE 0 END),
            ROUND(SUM(scalp_pnl_usd), 2)
        FROM trades
        WHERE scalp_pnl_usd IS NOT NULL AND status != 'EXCLUDED_ANOMALY'
        GROUP BY bucket
        ORDER BY bucket
    """)
    buckets = []
    for row in c.fetchall():
        b_n = row[1]
        b_wins = row[2] or 0
        b_wr, b_low, b_high = wilson_ci(b_wins, b_n)
        buckets.append({
            'bucket': row[0],
            'n': b_n,
            'wins': b_wins,
            'wr': b_wr * 100,
            'ci': (b_low * 100, b_high * 100),
            'pnl': row[3]
        })

    # Side breakdown
    c.execute("""
        SELECT side, COUNT(*), SUM(CASE WHEN scalp_pnl_usd > 0 THEN 1 ELSE 0 END), SUM(scalp_pnl_usd)
        FROM trades
        WHERE scalp_pnl_usd IS NOT NULL AND status != 'EXCLUDED_ANOMALY'
        GROUP BY side
    """)
    sides = []
    for row in c.fetchall():
        s_n = row[1]
        s_wins = row[2] or 0
        s_wr, s_low, s_high = wilson_ci(s_wins, s_n)
        sides.append({
            'side': row[0],
            'n': s_n,
            'wins': s_wins,
            'wr': s_wr * 100,
            'ci': (s_low * 100, s_high * 100),
            'pnl': round(row[3] or 0.0, 2)
        })

    # False stops
    c.execute("""
        SELECT COUNT(*) FROM trades
        WHERE exit_reason LIKE '%STOP_LOSS%' AND settled_pnl_usd > 0 AND status != 'EXCLUDED_ANOMALY'
    """)
    false_stops = c.fetchone()[0]

    return {
        'n': n_comp,
        'scalp_wins': scalp_wins,
        'scalp_wr': scalp_wr * 100,
        'scalp_ci': (scalp_wr_low * 100, scalp_wr_high * 100),
        'scalp_pnl': sum(scalp_pnl_vals),
        'scalp_ev': np.mean(scalp_pnl_vals) if scalp_pnl_vals else 0.0,
        'n_settled': n_settled,
        'settled_wins': settled_wins,
        'settled_wr': settled_wr * 100,
        'settled_ci': (settled_wr_low * 100, settled_wr_high * 100),
        'settled_pnl': sum(settled_pnl_vals),
        'settled_ev': np.mean(settled_pnl_vals) if settled_pnl_vals else 0.0,
        'mean_diff': mean_diff,
        't_stat': t_stat,
        'p_val': p_val,
        'current_equity': equity,
        'peak_equity': peak,
        'max_dd': max_dd,
        'max_dd_pct': max_dd_pct,
        'reasons': reasons,
        'buckets': buckets,
        'sides': sides,
        'false_stops': false_stops,
        'excluded_anomalies': excluded_anomalies
    }

def main():
    parser = argparse.ArgumentParser(description="Generate Rigorous Statistical Audit for Active Polymarket Engines")
    args = parser.parse_args()

    targets = [
        ("ENGINE 1: WITH BTC SPOT CONFIRMATION (>= $60)", BASE_DIR / "paper_trades.db", 60),
        ("ENGINE 2: PURE MOMENTUM (NO BTC CHECK)", BASE_DIR / "paper_trades_pure.db", 500)
    ]

    print("=" * 78)
    print("  🔬 POLYMARKET RIGOROUS STATISTICAL REPORT (ACTIVE ENGINES ONLY)")
    print("=" * 78)

    for title, db_file, target_n in targets:
        st = analyze_engine_db(db_file)
        if not st:
            print(f"\n[!] {title}: No trade data found in {db_file.name}")
            continue

        pct_target = (st['n'] / target_n) * 100
        print(f"\n{'#' * 78}")
        print(f"  {title}")
        print(f"  Database: {db_file.name} | Sample Size: N = {st['n']} ({pct_target:.1f}% of 1-week target N={target_n})")
        print(f"{'#' * 78}")

        print(f"\n1. PERFORMANCE & 95% WILSON CONFIDENCE INTERVALS:")
        print(f"   • Scalp Exit (20s) : {st['scalp_wins']}/{st['n']} Wins ({st['scalp_wr']:.1f}%) | 95% CI: [{st['scalp_ci'][0]:.1f}%, {st['scalp_ci'][1]:.1f}%]")
        print(f"     - Total PnL      : ${st['scalp_pnl']:+.2f} USD | EV: ${st['scalp_ev']:+.3f} USD/trade")
        print(f"   • Settled (Hold)   : {st['settled_wins']}/{st['n_settled']} Wins ({st['settled_wr']:.1f}%) | 95% CI: [{st['settled_ci'][0]:.1f}%, {st['settled_ci'][1]:.1f}%]")
        print(f"     - Total PnL      : ${st['settled_pnl']:+.2f} USD | EV: ${st['settled_ev']:+.3f} USD/trade")
        
        sig_str = "STATISTICALLY SIGNIFICANT (p < 0.05)" if st['p_val'] < 0.05 else "NOT SIGNIFICANT YET (p >= 0.05 - Variance/Sample size effect)"
        print(f"   • Hold vs Scalp    : Mean Diff: ${st['mean_diff']:+.3f}/trade | t={st['t_stat']:.2f}, p={st['p_val']:.3f} ({sig_str})")

        print(f"\n2. PORTFOLIO & RISK:")
        print(f"   • Current Equity   : ${st['current_equity']:.2f} USD (Peak: ${st['peak_equity']:.2f})")
        print(f"   • Max Drawdown     : -${st['max_dd']:.2f} USD (-{st['max_dd_pct']:.2f}%)")

        print(f"\n3. PRICE CORRIDORS (WILSON 95% CI):")
        for b in st['buckets']:
            print(f"   • [{b['bucket']}]: N={b['n']:2} | WR: {b['wr']:5.1f}% [{b['ci'][0]:4.1f}% - {b['ci'][1]:4.1f}%] | PnL: ${b['pnl']:+6.2f}")

        print(f"\n4. EXIT BREAKDOWN:")
        for r_name, r_data in st['reasons'].items():
            print(f"   • {r_name:<30}: N={r_data['count']:2} trades | PnL: ${r_data['pnl']:+6.2f}")
        print(f"   • False Stops (Resolved Win): {st['false_stops']} trades")
        if st.get('excluded_anomalies'):
            print(f"   • ⚠️ Excluded Anomalies        : {st['excluded_anomalies']} trade(s) (OOD fills purged from stats)")

    print("\n" + "=" * 78 + "\n")

if __name__ == "__main__":
    main()
