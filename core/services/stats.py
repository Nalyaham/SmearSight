import math


def wilson(k, n, z=1.96):
    """95% Wilson confidence interval for a proportion k/n."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0, (c - a) / d), min(1, (c + a) / d)]


def percentile(x, q):
    if not x:
        return None
    x = sorted(x)
    k = (len(x) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return x[f] if f == c else x[f] + (x[c] - x[f]) * (k - f)
