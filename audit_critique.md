# Critique: "Quantitative Audit — Implied Probability & Alpha Edge Decomposition"

Reviewing the v1.0 audit document (686/312 trade analysis) against the raw
claim: **+10.0 to +15.5pp edge, +$0.67–$0.70 EV/trade, "not an optical
illusion or statistical noise."**

Short version: the document is well-formatted but the core benchmark it
uses to prove "edge" is confounded, and several of the supporting numbers
(Kelly output, tiny-N buckets) are actually warning signs that got narrated
as confirmations instead.

---

## 1. The benchmark itself doesn't isolate signal (the main issue)

The entire "alpha edge" is defined as:

```
edge = realized_win_rate − entry_ask_price
```

This treats the entry ask as the market's final, informationally efficient
estimate of the outcome. But entry happens at T-150s and settlement happens
at T-0, and BTC keeps moving in between. **Any** strategy that buys the
side currently favored by the order book — including one with zero
predictive signal — will show a positive gap here, because the market's
true probability keeps updating toward the actual outcome as time passes.
That's not evidence the bot is smart; it's evidence that time resolves
uncertainty, which happens regardless of what triggered the entry.

**What's missing**: a naive control. Buy the favored side at a random
moment in the same 150s–60s window, same stake, same days, no momentum
filter — then compare *that* baseline's edge to the bot's edge. If the
bot's entry logic adds nothing beyond "buy the favorite and wait," the two
will look similar. The document never runs this comparison, so the
headline number can't currently be attributed to the bot's signal
specifically.

---

## 2. Tiny-N buckets are given equal visual weight to real ones

| Bucket | N | Reported edge |
|---|---|---|
| $0.55 | 3 | +43.3 pp |
| $0.60 | 2 | +35.5 pp |
| $0.70 | 181 | +15.5 pp |

A 2–3 trade bucket showing "+43.3pp" isn't a finding — it's what small
samples do. These sit in the same table, same bold formatting, as the
181-trade bucket, which visually props up the "robust across the corridor"
narrative. They should either be excluded or clearly flagged as
statistically meaningless.

---

## 3. No confidence intervals anywhere

For the flagship $0.70 bucket (N=181, realized 88.4% settled WR), the
binomial standard error is roughly ±5.6pp — a rough 95% CI lands near
[77%, 100%]. That still clears the 72.9% implied line, which is actually a
reasonable sign for that bucket specifically. But the smaller buckets
(N=34, N=48, N=2, N=3) have CIs wide enough to swallow the claimed edge
entirely, and the document reports every bucket's point estimate with the
same confidence, positive or negative, without ever computing this.

---

## 4. Pre-fix and post-fix data pooled into one "confirmation" set

The "Grand Consolidated" 686-trade table mixes Runs 1–2 (before the VWAP
depth check and dynamic slippage fixes) with Runs 3–5 (after). These are
two different simulators. Presenting their pooled output as a single
686-trade validation obscures whether the fixes changed the result at all
— which was the entire point of making them.

---

## 5. The Kelly output (f* ≈ 1.01) is a red flag, not a confirmation

Full Kelly telling you to stake slightly *more than 100% of equity* per
trade is a classic symptom of overfit or noisy win-rate/win-size inputs,
not a sign of a strong, safe edge. The document takes f* = 1.01 and simply
fractions it down to "10% Kelly," treating the extreme output as
mildly-too-aggressive-but-basically-sound. A more honest read: when naive
Kelly exceeds 1.0, the inputs feeding it are suspect, and that should
prompt re-checking the win-rate/edge numbers before sizing off them at all.

---

## 6. The $0.75 bucket breaks the pattern and isn't addressed

Both tables show a negative *scalp* edge specifically at $0.75
(-4.3pp and -7.2pp), sandwiched between positive edges at $0.70 and $0.80.
A genuine structural effect (e.g., near-expiry convergence, latency lag)
should move smoothly across adjacent price buckets. A dip-then-recovery
pattern is more consistent with noise than mechanism, and the document
doesn't mention or explain it.

---

## 7. The "why the edge exists" mechanisms are asserted, not measured

Three explanations are given — cross-exchange latency lag, retail
underreaction near expiry, liquidity asymmetry pushing bid up after entry —
all plausible on priors. But none are backed by data in this document: no
measured Binance/Coinbase-to-Polymarket lag, no retail order-flow data, no
bid-ask evolution data after entry. They're presented with the same
confidence as the measured win-rate tables, which makes the report read as
more mechanistically settled than it actually is.

---

## What would actually move this from "plausible" to "confirmed"

1. **Run the naive-favorite-buyer control** over the same 3 days / same
   stake, and report edge relative to *that*, not just relative to entry
   price.
2. **Drop or flag buckets under ~20 trades** rather than reporting them
   with full-precision edge numbers.
3. **Report confidence intervals** next to every edge figure.
4. **Separate pre-fix and post-fix runs** rather than pooling them into one
   "Grand Total."
5. **Investigate the $0.75 dip** specifically — if it doesn't resolve with
   more data, that's evidence against a clean structural story.
6. **Re-derive Kelly sizing** only after the above, since the current f*
   estimate is likely distorted by the same noise affecting the edge
   figures.

Until #1 is done, "+$0.70/trade, not statistical noise" is not
substantiated by this document — the gap it measures is consistent with
*both* "genuine signal" and "no signal, just time-decay toward the true
outcome," and it doesn't distinguish between them.
