from typing import Any

def _to_ba(x: Any) -> bytearray:
    return x if isinstance(x, bytearray) else bytearray(x)

def _clip(ba: bytearray, max_size: int) -> bytearray:
    if len(ba) > max_size:
        del ba[max_size:]
    return ba

def op_nop(buf, add_buf, max_size, rng=None, **kw):
    # 입력 그대로 복사 반환
    return _clip(bytearray(buf), max_size)

def op_flip_bool(buf, add_buf, max_size, rng=None, **kw):
    # "true"/"false" 한 번 토글 (텍스트 기반)
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        if ("true" in s) or ("false" in s):
            import random as _rnd
            r = (rng.random() if rng else _rnd.random())
            if ("true" in s) and (r < 0.5 or "false" not in s):
                s = s.replace("true", "false", 1)
            elif "false" in s:
                s = s.replace("false", "true", 1)
            ba = bytearray(s.encode("utf-8", errors="ignore"))
            return _clip(ba, max_size)
    except Exception:
        pass
    return _clip(bytearray(buf), max_size)

def op_num_boundary(buf, add_buf, max_size, rng=None, **kw):
    # 정수 하나를 경계값으로 치환
    import re, random as _rnd
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        nums = list(re.finditer(r"-?\d+", s))
        if not nums:
            return _clip(bytearray(buf), max_size)
        i = int((rng.random() if rng else _rnd.random()) * len(nums))
        m = nums[i]
        boundaries = ["0","1","-1","2147483647","-2147483648","4294967295"]
        v = boundaries[int((rng.random() if rng else _rnd.random()) * len(boundaries)) % len(boundaries)]
        s2 = s[:m.start()] + v + s[m.end():]
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

# 연산자 목록 (Phase A: [0,1], Phase B: [0,2], Phase C: 전부)
OPS = [op_nop, op_flip_bool, op_num_boundary]

__all__ = ["OPS", "op_nop", "op_flip_bool", "op_num_boundary"]
