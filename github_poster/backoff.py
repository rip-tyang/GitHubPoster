import random

def exp_backoff_with_jitter(base, cap, attempt):
    return min(cap, base * 2 ** (attempt - 1)) * (1 + random.random())