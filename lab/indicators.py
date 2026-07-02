"""Basic indicators (pure Python, no deps)."""
import statistics


def sma(values, n, i):
    if i + 1 < n:
        return None
    return sum(values[i - n + 1:i + 1]) / n


def annualized_vol(closes, window=60):
    if len(closes) < window + 1:
        window = len(closes) - 1
    rets = [closes[k] / closes[k - 1] - 1 for k in range(len(closes) - window, len(closes))]
    if len(rets) < 2:
        return 0.0
    return statistics.pstdev(rets) * (252 ** 0.5) * 100
