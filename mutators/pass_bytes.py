import sys

_loaded_from = __file__
_printed = False
_calls = 0

def init(seed):
    global _printed
    if not _printed:
        print(f"[py-mut] loaded: {_loaded_from}", file=sys.stderr, flush=True)
        _printed = True
    return 0

def _to_bytes(x):
    if x is None:
        return b""
    # 어떤 버퍼 타입이 와도 bytes로 보정 (memoryview/bytearray/bytes 등)
    try:
        return memoryview(x).tobytes()
    except TypeError:
        return bytes(x)

def fuzz(buf, add_buf, max_size):
    global _calls
    data = _to_bytes(buf)

    # 길이 보정
    if max_size is None or max_size <= 0:
        max_size = 1
    if not data:
        data = b"X"
    if len(data) > max_size:
        data = data[:max_size]

    # 처음 몇 번만 디버그 로그(표준에러로) — 너무 많이 찍히면 느려짐
    if _calls < 3:
        print(f"[py-mut] call#{_calls}: in={type(buf).__name__} -> out=bytes len={len(data)} max={max_size}",
              file=sys.stderr, flush=True)
    _calls += 1

    return data

def deinit():
    pass