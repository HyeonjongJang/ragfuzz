import random
_rng = random.Random()
def init(seed=None):
    try:
        if seed is not None: _rng.seed(int(seed))
    except Exception: pass
    return 0
def fuzz(buf, add_buf, max_size):
    try:
        b = bytearray(buf)
        if b: b[_rng.randrange(len(b))] ^= 1  # 한 바이트만 토글
        if len(b) > int(max_size): del b[int(max_size):]
        return bytes(b)
    except Exception:
        try: return bytes(buf)
        except Exception: return b"{}"
def deinit(): return 0
