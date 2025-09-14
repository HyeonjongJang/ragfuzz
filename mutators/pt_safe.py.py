def init(seed): 
    return 0

def _to_bytes(x):
    if isinstance(x, (bytes, bytearray)):
        return bytes(x)
    tb = getattr(x, "tobytes", None)
    if tb:
        try:
            return tb()
        except Exception:
            pass
    return bytes(x)

def fuzz(buf, add_buf, max_size):
    data = _to_bytes(buf) or b"X"
    if max_size and len(data) > max_size:
        data = data[:max_size]
    return bytearray(data)

def deinit():
    pass
