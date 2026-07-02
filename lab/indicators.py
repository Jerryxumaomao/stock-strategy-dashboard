"""Basic indicators (pure Python, no deps)."""
import statistics


def sma(values, n, i):
    if i + 1 < n:
        return None
    return sum(values[i - n + 1:i + 1]) / n


def atr(H, L, C, i, n=14):
    """Average True Range at bar i (needs prior closes)."""
    trs = []
    for k in range(max(1, i - n + 1), i + 1):
        trs.append(max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1])))
    return sum(trs) / len(trs) if trs else 0.0


def annualized_vol(closes, window=60):
    if len(closes) < window + 1:
        window = len(closes) - 1
    rets = [closes[k] / closes[k - 1] - 1 for k in range(len(closes) - window, len(closes))]
    if len(rets) < 2:
        return 0.0
    return statistics.pstdev(rets) * (252 ** 0.5) * 100
