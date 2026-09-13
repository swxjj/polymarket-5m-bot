// Polymarket 5m BTC Momentum Radar Dashboard Client
// Polls /api/status and updates DOM and Canvas in real-time

const POLL_INTERVAL_MS = 1000;

const state = {
  equityHistory: [100.0],
  lastUpdate: null,
};

function updateClock() {
  const now = new Date();
  const utcStr = now.toISOString().slice(11, 19) + ' UTC';
  const el = document.getElementById('clock-utc');
  if (el) el.textContent = utcStr;
}
setInterval(updateClock, 1000);
updateClock();

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    const st = document.getElementById('ws-status');
    if (st) {
      st.textContent = 'RECONNECTING...';
      st.style.color = '#f43f5e';
    }
  }
}

function formatUSD(val, plus = false) {
  if (val === null || val === undefined || isNaN(val)) return '$0.00';
  const s = Math.abs(val).toFixed(2);
  if (val > 0 && plus) return `+$${s}`;
  if (val < 0) return `-$${s}`;
  return `$${s}`;
}

function formatPct(val, plus = false) {
  if (val === null || val === undefined || isNaN(val)) return '0.00%';
  const s = Math.abs(val).toFixed(2);
  if (val > 0 && plus) return `+${s}%`;
  if (val < 0) return `-${s}%`;
  return `${s}%`;
}

function renderDashboard(data) {
  const { capital, active_market, active_position, stats, recent_trades, config } = data;

  // 1. Header Status
  const statusEl = document.getElementById('ws-status');
  if (statusEl) {
    statusEl.textContent = 'LIVE CLOB FEED';
    statusEl.style.color = '#10b981';
  }

  // 2. Capital Metrics
  if (capital) {
    const eq = capital.current_equity || 100.0;
    const startCap = capital.starting_capital || 100.0;
    const eqChange = ((eq - startCap) / startCap) * 100;

    const elEq = document.getElementById('val-equity');
    const elEqChange = document.getElementById('val-equity-change');
    const elStartCap = document.getElementById('val-start-cap');
    const elCash = document.getElementById('val-cash');

    if (elEq) elEq.textContent = formatUSD(eq);
    if (elStartCap) elStartCap.textContent = formatUSD(startCap);
    if (elCash) elCash.textContent = formatUSD(capital.available_cash);

    if (elEqChange) {
      elEqChange.textContent = formatPct(eqChange, true);
      elEqChange.className = `badge ${eqChange >= 0 ? 'badge-profit' : 'badge-loss'}`;
    }

    // Chart header stat
    const chartEq = document.getElementById('chart-equity-stat');
    if (chartEq) chartEq.textContent = formatUSD(eq);

    // Update equity history
    if (capital.equity_history && Array.isArray(capital.equity_history)) {
      state.equityHistory = capital.equity_history;
    } else {
      state.equityHistory.push(eq);
      if (state.equityHistory.length > 50) state.equityHistory.shift();
    }
  }

  // 3. Scalp PnL Metrics
  if (stats) {
    const elScalpPnl = document.getElementById('val-scalp-pnl');
    const elScalpWinrate = document.getElementById('val-scalp-winrate');
    const elScalpTrades = document.getElementById('val-scalp-trades');
    const elScalpWl = document.getElementById('val-scalp-wl');

    if (elScalpPnl) {
      elScalpPnl.textContent = formatUSD(stats.total_scalp_pnl, true);
      elScalpPnl.style.color = stats.total_scalp_pnl >= 0 ? '#10b981' : '#f43f5e';
    }
    if (elScalpWinrate) {
      elScalpWinrate.textContent = `${stats.scalp_win_rate_pct || 0}% Win`;
      elScalpWinrate.className = `badge ${stats.scalp_win_rate_pct >= 50 ? 'badge-profit' : 'badge-neutral'}`;
    }
    if (elScalpTrades) elScalpTrades.textContent = stats.total_trades || 0;
    if (elScalpWl) elScalpWl.textContent = `${stats.scalp_wins || 0}W / ${stats.scalp_losses || 0}L`;

    // Benchmark stats
    const elSettledPnl = document.getElementById('val-settled-pnl');
    const elSettledWinrate = document.getElementById('val-settled-winrate');
    const elSettledCount = document.getElementById('val-settled-count');
    const elAlpha = document.getElementById('val-alpha');

    if (elSettledPnl) {
      elSettledPnl.textContent = formatUSD(stats.total_settled_pnl, true);
      elSettledPnl.style.color = stats.total_settled_pnl >= 0 ? '#10b981' : '#f43f5e';
    }
    if (elSettledWinrate) {
      elSettledWinrate.textContent = `${stats.settled_win_rate_pct || 0}% Win`;
    }
    if (elSettledCount) elSettledCount.textContent = stats.settled_trades || 0;
    if (elAlpha) {
      const alpha = (stats.total_scalp_pnl || 0) - (stats.total_settled_pnl || 0);
      elAlpha.textContent = formatUSD(alpha, true);
      elAlpha.style.color = alpha >= 0 ? '#10b981' : '#f43f5e';
    }
  }

  // 4. Exposure & Position Card
  const elExposure = document.getElementById('val-active-exposure');
  const elPosBadge = document.getElementById('val-position-badge');
  const elUnrealized = document.getElementById('val-unrealized-pnl');

  if (active_position) {
    if (elExposure) elExposure.textContent = formatUSD(active_position.stake_usd);
    if (elPosBadge) {
      elPosBadge.textContent = `${active_position.side} ACTIVE`;
      elPosBadge.className = `badge ${active_position.side === 'UP' ? 'badge-up' : 'badge-down'}`;
    }
    if (elUnrealized) {
      const unPnl = active_position.unrealized_pnl_usd || 0;
      elUnrealized.textContent = formatUSD(unPnl, true);
      elUnrealized.style.color = unPnl >= 0 ? '#10b981' : '#f43f5e';
    }
  } else {
    if (elExposure) elExposure.textContent = '$0.00';
    if (elPosBadge) {
      elPosBadge.textContent = 'NO POSITION';
      elPosBadge.className = 'badge badge-neutral';
    }
    if (elUnrealized) {
      elUnrealized.textContent = '$0.00';
      elUnrealized.style.color = 'var(--color-text-dim)';
    }
  }

  // 5. Market Header & 5m Candle Timeline
  if (active_market) {
    const elTitle = document.getElementById('market-title');
    const elSlug = document.getElementById('market-slug');
    const elSec = document.getElementById('seconds-left');
    const elProgress = document.getElementById('timeline-progress');

    if (elTitle) elTitle.textContent = active_market.title || 'Bitcoin 5-Minute Event';
    if (elSlug) elSlug.textContent = active_market.slug || 'btc-updown-5m-...';

    const secLeft = active_market.seconds_left || 0;
    if (elSec) elSec.textContent = Math.max(0, Math.round(secLeft));

    // Progress of 300s candle
    const elapsed = Math.max(0, Math.min(300, 300 - secLeft));
    const pct = (elapsed / 300) * 100;
    if (elProgress) elProgress.style.width = `${pct}%`;

    // 6. UP & DOWN Orderbook Quotes
    const upAsk = active_market.up_ask;
    const upBid = active_market.up_bid;
    const dnAsk = active_market.down_ask;
    const dnBid = active_market.down_bid;

    document.getElementById('up-ask').textContent = upAsk !== null ? `$${upAsk.toFixed(2)}` : '--';
    document.getElementById('up-bid').textContent = upBid !== null ? `$${upBid.toFixed(2)}` : '--';
    document.getElementById('up-spread').textContent = (upAsk !== null && upBid !== null) ? `$${(upAsk - upBid).toFixed(2)}` : '--';
    document.getElementById('up-implied').textContent = upAsk !== null ? `${Math.round(upAsk * 100)}%` : '--';
    const upBar = document.getElementById('up-bar');
    if (upBar) upBar.style.width = `${Math.min(100, Math.max(0, (upAsk || 0.5) * 100))}%`;

    document.getElementById('down-ask').textContent = dnAsk !== null ? `$${dnAsk.toFixed(2)}` : '--';
    document.getElementById('down-bid').textContent = dnBid !== null ? `$${dnBid.toFixed(2)}` : '--';
    document.getElementById('down-spread').textContent = (dnAsk !== null && dnBid !== null) ? `$${(dnAsk - dnBid).toFixed(2)}` : '--';
    document.getElementById('down-implied').textContent = dnAsk !== null ? `${Math.round(dnAsk * 100)}%` : '--';
    const dnBar = document.getElementById('down-bar');
    if (dnBar) dnBar.style.width = `${Math.min(100, Math.max(0, (dnAsk || 0.5) * 100))}%`;

    // Highlight card if within target entry range (e.g. 0.70 - 0.88)
    const cardUp = document.getElementById('quote-up');
    const cardDown = document.getElementById('quote-down');
    const minThresh = config?.threshold || 0.70;
    const maxThresh = config?.max_entry_ask || 0.88;
    if (cardUp) cardUp.style.borderColor = (upAsk >= minThresh && upAsk <= maxThresh) ? 'var(--accent-up)' : 'var(--border-subtle)';
    if (cardDown) cardDown.style.borderColor = (dnAsk >= minThresh && dnAsk <= maxThresh) ? 'var(--accent-down)' : 'var(--border-subtle)';
  }

  // 6b. Signal Indicators (BTC Spot & Skew)
  const btcSpotEl = document.getElementById('btc-spot-display');
  if (btcSpotEl && data.btc_spot) {
    const cur = data.btc_spot.current || 0;
    const delta = data.btc_spot.delta || 0;
    const sign = delta >= 0 ? '+' : '';
    const color = delta >= 0 ? '#10b981' : '#f43f5e';
    btcSpotEl.innerHTML = `$${cur.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})} <span style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); color: ${color}; font-weight: 700;">${sign}$${Math.abs(delta).toFixed(2)}</span>`;
  }

  const skewEl = document.getElementById('market-skew-display');
  if (skewEl && active_market && active_market.skew !== undefined) {
    const upPct = Math.round(active_market.skew * 100);
    const dnPct = 100 - upPct;
    skewEl.innerHTML = `<span style="color: #10b981; font-weight: 700;">UP ${upPct}%</span> / <span style="color: #f43f5e; font-weight: 700;">DN ${dnPct}%</span>`;
  }

  const lockBadge = document.getElementById('candle-lock-badge');
  if (lockBadge) {
    if (data.candle_locked) {
      lockBadge.textContent = '1 TRADE/CANDLE: LOCKED';
      lockBadge.style.background = 'rgba(244, 63, 94, 0.2)';
      lockBadge.style.color = '#f43f5e';
    } else {
      lockBadge.textContent = '1 TRADE/CANDLE: READY';
      lockBadge.style.background = 'rgba(16, 185, 129, 0.2)';
      lockBadge.style.color = '#10b981';
    }
  }

  const hedgeBadge = document.getElementById('hedge-status-badge');
  if (hedgeBadge) {
    if (active_position && active_position.has_hedge) {
      hedgeBadge.textContent = `HEDGED (${active_position.hedge_side})`;
      hedgeBadge.style.background = 'rgba(16, 185, 129, 0.2)';
      hedgeBadge.style.color = '#10b981';
    } else if (config?.enable_hedge) {
      hedgeBadge.textContent = `HEDGE: ARMED (>=${config.hedge_trigger_price || 0.93})`;
      hedgeBadge.style.background = 'rgba(99, 102, 241, 0.2)';
      hedgeBadge.style.color = '#818cf8';
    } else {
      hedgeBadge.textContent = 'HEDGE: OFF';
      hedgeBadge.style.background = 'rgba(255, 255, 255, 0.06)';
      hedgeBadge.style.color = '#94a3b8';
    }
  }

  // 7. Position Cockpit
  renderCockpit(active_position, active_market);

  // 8. Equity Curve Canvas
  drawEquityChart();

  // 9. Trades Table
  renderTradesTable(recent_trades);
}

function renderCockpit(pos, mkt) {
  const body = document.getElementById('cockpit-body');
  const statusBadge = document.getElementById('cockpit-status');
  if (!body) return;

  if (!pos) {
    if (statusBadge) {
      statusBadge.textContent = 'SCANNING CANDLE';
      statusBadge.style.color = '#94a3b8';
    }
    body.innerHTML = `
      <div class="idle-state">
        <div class="radar-spinner"></div>
        <div class="idle-title">Scanning 5-Minute Polymarket Order Book</div>
        <div class="idle-desc">Monitoring for momentum impulse. Enters automatically when best ask is between <strong>$0.70 and $0.88</strong> with confirmed <strong>BTC impulse (&ge;$60)</strong>, supporting skew, and max 1 trade per candle.</div>
      </div>
    `;
    return;
  }

  if (statusBadge) {
    statusBadge.textContent = `POSITION OPEN (${pos.side})`;
    statusBadge.style.color = pos.side === 'UP' ? '#10b981' : '#f43f5e';
  }

  const unPnl = pos.unrealized_pnl_usd || 0;
  const pnlPct = pos.unrealized_pnl_pct || 0;
  const pnlClass = unPnl >= 0 ? 'color: #10b981' : 'color: #f43f5e';

  body.innerHTML = `
    <div class="active-pos-box ${pos.side === 'UP' ? 'pos-up' : 'pos-down'}">
      <div class="pos-stat">
        <span class="label">OUTCOME / SHARES</span>
        <span class="val">${pos.side} (${pos.shares.toFixed(2)} sh)</span>
      </div>
      <div class="pos-stat">
        <span class="label">ENTRY ASK &rarr; CURRENT BID</span>
        <span class="val">$${pos.entry_ask.toFixed(2)} &rarr; $${pos.current_bid ? pos.current_bid.toFixed(2) : '--'}</span>
      </div>
      <div class="pos-stat">
        <span class="label">FLOATING PNL</span>
        <span class="val" style="${pnlClass}">${formatUSD(unPnl, true)} (${formatPct(pnlPct, true)})</span>
      </div>
      <div class="pos-stat">
        <span class="label">STOP-LOSS / EXIT</span>
        <span class="val">SL: $${pos.stop_loss_price.toFixed(3)} | Exit: &le;20s</span>
      </div>
      ${pos.has_hedge ? `
      <div class="pos-stat" style="grid-column: span 2; background: rgba(16, 185, 129, 0.12); border: 1px dashed rgba(16, 185, 129, 0.5); border-radius: 6px; padding: 6px 10px;">
        <span class="label" style="color: #10b981; font-weight: 700;">🛡️ ASYMMETRIC MICRO-HEDGE ACTIVE</span>
        <span class="val" style="color: #10b981;">Hedged on ${pos.hedge_side} (${pos.hedge_shares?.toFixed(1)} shares @ $${pos.hedge_entry_ask?.toFixed(3)}) | Stake: $${pos.hedge_stake_usd?.toFixed(2)}</span>
      </div>` : ''}
    </div>
  `;
}

function drawEquityChart() {
  const canvas = document.getElementById('equity-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  const data = state.equityHistory;
  if (!data || data.length < 2) {
    // Draw baseline
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();
    return;
  }

  const minVal = Math.min(...data) * 0.995;
  const maxVal = Math.max(...data) * 1.005;
  const range = (maxVal - minVal) || 1;

  const points = data.map((val, i) => {
    const x = (i / (data.length - 1)) * (w - 20) + 10;
    const y = h - 20 - ((val - minVal) / range) * (h - 40);
    return { x, y };
  });

  // Background gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(99, 102, 241, 0.35)');
  grad.addColorStop(1, 'rgba(99, 102, 241, 0.0)');

  ctx.beginPath();
  ctx.moveTo(points[0].x, h);
  points.forEach(p => ctx.lineTo(p.x, p.y));
  ctx.lineTo(points[points.length - 1].x, h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Stroke line
  ctx.beginPath();
  points.forEach((p, i) => {
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // Glow on last point
  const last = points[points.length - 1];
  ctx.beginPath();
  ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
  ctx.fillStyle = '#f7931a';
  ctx.fill();
}

function renderTradesTable(trades) {
  const tbody = document.getElementById('trades-tbody');
  const countEl = document.getElementById('table-count');
  if (!tbody) return;

  if (!trades || trades.length === 0) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-state">No completed trades recorded yet. System is monitoring live markets...</td></tr>`;
    if (countEl) countEl.textContent = '0 recorded sessions';
    return;
  }

  if (countEl) countEl.textContent = `${trades.length} recorded session${trades.length > 1 ? 's' : ''}`;

  tbody.innerHTML = trades.map(t => {
    const pnl = t.scalp_pnl_usd;
    const pnlClass = pnl >= 0 ? 'badge-profit' : 'badge-loss';
    const sideBadge = t.side === 'UP' ? 'badge-up' : 'badge-down';
    const timeStr = t.entry_time ? t.entry_time.slice(11, 19) : '--';
    const settledPnl = t.settled_pnl_usd !== null ? formatUSD(t.settled_pnl_usd, true) : '--';
    const winner = t.resolved_winner || 'PENDING';

    return `
      <tr>
        <td>${timeStr}</td>
        <td><span style="color: var(--accent-indigo)">${t.market_slug.replace('btc-updown-5m-', '')}</span></td>
        <td><span class="badge ${sideBadge}">${t.side}</span></td>
        <td>$${(t.entry_ask || 0).toFixed(2)}</td>
        <td style="color: var(--color-text-dim)">$${(t.spread_at_entry || 0).toFixed(2)}</td>
        <td>${t.exit_bid !== null ? `$${t.exit_bid.toFixed(2)}` : '--'}</td>
        <td style="font-size: 0.72rem">${t.exit_reason || 'IN FLIGHT'}</td>
        <td><span class="badge ${pnlClass}">${pnl !== null ? formatUSD(pnl, true) : '--'}</span></td>
        <td><span style="color: ${winner === t.side ? '#10b981' : '#94a3b8'}">${winner} (${settledPnl})</span></td>
        <td><span class="badge ${t.status === 'CLOSED' ? 'badge-neutral' : 'badge-up'}">${t.status}</span></td>
      </tr>
    `;
  }).join('');
}

// Start polling
setInterval(fetchStatus, POLL_INTERVAL_MS);
fetchStatus();
