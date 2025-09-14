import importlib

# 원래 모듈을 가져옵니다.
_under = importlib.import_module("mutators.pass_through")

def init(seed):
    if hasattr(_under, "init"):
        try:
            return int(_under.init(seed) or 0)
        except Exception:
            return 0
    return 0

def fuzz(buf, add_buf, max_size):
    try:
        out = _under.fuzz(buf, add_buf, max_size)
        # 타입 강제
        if isinstance(out, memoryview):
            out = out.tobytes()
        elif not isinstance(out, (bytes, bytearray)):
            out = bytes(out)  # numpy array 등도 커버
        # 길이 clamp (가장 중요!)
        if len(out) > max_size:
            out = out[:max_size]
        return bytes(out)
    except Exception:
        # 예외 시 원본을 안전하게 반환
        return bytes(buf[:max_size])

def deinit():
    if hasattr(_under, "deinit"):
        try:
            _under.deinit()
        except Exception:
            pass