import sys
_printed=False; _calls=0
def init(seed):
    global _printed
    if not _printed:
        print("[py-mut] loaded(pass_bytes_ba)", file=sys.stderr, flush=True)
        _printed=True
    return 0

def _to_bytes(x):
    if isinstance(x,(bytes,bytearray)): return bytes(x)
    tb = getattr(x,"tobytes", None)
    if tb: 
        try: return tb()
        except Exception: pass
    return bytes(x)

def fuzz(buf, add_buf, max_size):
    global _calls
    data = _to_bytes(buf)
    if not data: data = b"X"
    if max_size and len(data) > max_size:
        data = data[:max_size]
    if _calls < 3:
        print(f"[py-mut] call#{_calls}: in={type(buf).__name__} -> out=bytearray len={len(data)}", file=sys.stderr, flush=True)
    _calls += 1
    return bytearray(data)

def deinit(): pass
