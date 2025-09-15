from typing import Any
import re
import random as _rnd

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_ba(x: Any) -> bytearray:
    return x if isinstance(x, bytearray) else bytearray(x)

def _clip(ba: bytearray, max_size: int) -> bytearray:
    if len(ba) > max_size:
        del ba[max_size:]
    return ba

def _r(rng):
    return (rng.random() if rng else _rnd.random())

def _ri(rng, lo: int, hi: int) -> int:
    # inclusive [lo, hi]
    if hi <= lo:
        return lo
    return int(lo + (_r(rng) * (hi - lo + 1)))

def _insert_before_last(s: str, closer: str, payload: str) -> str:
    """Insert payload right before last 'closer' char if present; else append."""
    idx = s.rfind(closer)
    if idx == -1:
        return s + payload
    return s[:idx] + payload + s[idx:]

def _extract_between(s: str, open_ch: str, close_ch: str):
    """Return substring between first open_ch and last close_ch, or None."""
    a = s.find(open_ch)
    b = s.rfind(close_ch)
    if a == -1 or b == -1 or b <= a:
        return None
    return s[a + 1 : b]

# ─────────────────────────────────────────────────────────────────────────────
# Base operators (Phase A: [0,1], Phase B: [0,2], Phase C: 전부)
# ─────────────────────────────────────────────────────────────────────────────

def op_nop(buf, add_buf, max_size, rng=None, **kw):
    """입력 그대로 복사 반환"""
    return _clip(bytearray(buf), max_size)

def op_flip_bool(buf, add_buf, max_size, rng=None, **kw):
    """텍스트 기반 "true"/"false" 1회 토글"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        if ("true" in s) or ("false" in s):
            r = _r(rng)
            if ("true" in s) and (r < 0.5 or "false" not in s):
                s = s.replace("true", "false", 1)
            elif "false" in s:
                s = s.replace("false", "true", 1)
            return _clip(bytearray(s.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        pass
    return _clip(bytearray(buf), max_size)

def op_num_boundary(buf, add_buf, max_size, rng=None, **kw):
    """정수 하나를 경계값으로 치환"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        nums = list(re.finditer(r"-?\d+", s))
        if not nums:
            return _clip(bytearray(buf), max_size)
        i = _ri(rng, 0, len(nums) - 1)
        m = nums[i]
        boundaries = [
            "0","1","-1",
            "2147483647","-2147483648",        # int32
            "4294967295",                      # uint32
            "9007199254740991",                # 2^53-1 (JS max safe int)
            "9007199254740993",                # 2^53+1 (precision edge)
            "1e308","-1e308","1e309","-1e309"  # big float-ish
        ]
        v = boundaries[_ri(rng, 0, len(boundaries) - 1)]
        s2 = s[:m.start()] + v + s[m.end():]
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

# 연산자 목록 (Phase A: [0,1], Phase B: [0,2], Phase C: 전부)
OPS = [op_nop, op_flip_bool, op_num_boundary]

# ─────────────────────────────────────────────────────────────────────────────
# Extended operator pack v1 (Phase B/C 강화)
# ─────────────────────────────────────────────────────────────────────────────

def op_fix_basic(buf, add_buf, max_size, rng=None, **kw):
    """
    가벼운 보정:
      - ,} -> } / ,] -> ]
      - 괄호 개수 불일치 시 닫힘 괄호 보충(최대 3개)
    """
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        s = s.replace(",}", "}").replace(", ]", "]").replace(",]", "]")
        open_o = s.count("{"); close_o = s.count("}")
        open_a = s.count("["); close_a = s.count("]")
        if open_o > close_o:
            s += "}" * min(3, open_o - close_o)
        if open_a > close_a:
            s += "]" * min(3, open_a - close_a)
        return _clip(bytearray(s.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_rare_token(buf, add_buf, max_size, rng=None, **kw):
    """
    희귀 키/토큰 삽입: "$schema", "__proto__", "constructor", "NaN", "Infinity" 등
    (일부 파서는 비표준 토큰에 취약)
    """
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        cand = [
            '"$schema":"http://example.com/schema.json"',
            '"__proto__":{}',
            '"constructor":{}',
            '"numNaN":NaN',
            '"posInf":Infinity',
            '"negInf":-Infinity',
        ]
        pick = cand[_ri(rng, 0, len(cand) - 1)]
        if "}" in s:
            ins = ("," if s.rfind("{") < s.rfind("}") - 1 else "") + pick
            s2 = _insert_before_last(s, "}", ins)
        else:
            s2 = "{" + pick + "}"
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_long_string(buf, add_buf, max_size, rng=None, **kw):
    """매우 긴 문자열 삽입 (1~4KB)"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        L = _ri(rng, 1024, 4096)
        payload = '"long":"' + ("A" * L) + '"'
        if "}" in s:
            ins = ("," if s.rfind("{") < s.rfind("}") - 1 else "") + payload
            s2 = _insert_before_last(s, "}", ins)
        else:
            s2 = "{%s}" % payload
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_deep_nest(buf, add_buf, max_size, rng=None, **kw):
    """깊은 중첩 감싸기: {"x":{"x":...,"v":<원본>...}}"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        depth = _ri(rng, 2, 8)
        pre = "{"
        for _ in range(depth):
            pre += '"x":{'
        mid = '"v":' + s
        post = "}" * (depth + 1)
        s2 = pre + mid + post
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_utf8_edge(buf, add_buf, max_size, rng=None, **kw):
    """UTF-8 경계: 잘린 멀티바이트/overlong/서러게이트 유사 바이트 삽입"""
    try:
        ba = bytearray(buf)
        junk = [
            b"\xC0\xAF",            # overlong '/'
            b"\xE2",                # dangling lead
            b"\xF0\x80\x80\x41",    # overlong 'A'
            b"\xED\xA0\x80",        # lone surrogate lead
            b"\xEF\xBB",            # half BOM
        ]
        pick = bytearray(junk[_ri(rng, 0, len(junk) - 1)])
        pos = _ri(rng, 0, max(0, len(ba)))
        ba[pos:pos] = pick
        return _clip(ba, max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

_key_re = re.compile(r'"([A-Za-z0-9_\-\$\.\:]+)"\s*:\s*')

def op_dup_keys(buf, add_buf, max_size, rng=None, **kw):
    """객체 내 임의 key를 복제하여 중복 키 삽입"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        if "}" not in s:
            return _clip(bytearray(buf), max_size)
        keys = list(_key_re.finditer(s))
        if not keys:
            return _clip(bytearray(buf), max_size)
        m = keys[_ri(rng, 0, len(keys) - 1)]
        key = m.group(1)
        val = _rnd.choice(["null", "true", "false", "0", "1", "-1", "\"dup\""])
        ins = f',"{key}":{val}'
        s2 = _insert_before_last(s, "}", ins)
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_add_field(buf, add_buf, max_size, rng=None, **kw):
    """새 필드 삽입 (경계 숫자/불리언/null)"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        k = f'"k{_ri(rng, 0, 9999)}"'
        v = _rnd.choice([
            "null", "true", "false",
            "0", "1", "-1",
            "2147483647", "-2147483648",  # int32
            "9007199254740993"            # 2^53+1
        ])
        payload = f'{k}:{v}'
        if "}" in s:
            ins = ("," if s.rfind("{") < s.rfind("}") - 1 else "") + payload
            s2 = _insert_before_last(s, "}", ins)
        else:
            s2 = "{"+payload+"}"
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_delete_field(buf, add_buf, max_size, rng=None, **kw):
    """임의 key:value 한 쌍 삭제(러프한 정규식 기반)"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        pairs = list(re.finditer(r'"[A-Za-z0-9_\-\$\.\:]+"\s*:\s*[^,}]*', s))
        if not pairs:
            return _clip(bytearray(buf), max_size)
        m = pairs[_ri(rng, 0, len(pairs) - 1)]
        end = m.end()
        if end < len(s) and s[end:end+1] == ",":
            end += 1
        s2 = s[:m.start()] + s[end:]
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_splice_objects(buf, add_buf, max_size, rng=None, **kw):
    """다른 시드(add_buf)의 객체 필드 일부를 현재 객체에 합침"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        if not add_buf:
            return _clip(bytearray(buf), max_size)
        t = bytes(add_buf).decode("utf-8", errors="ignore")
        src = _extract_between(t, "{", "}")
        if src is None:
            return _clip(bytearray(buf), max_size)
        if "}" in s:
            ins = ("," if s.rfind("{") < s.rfind("}") - 1 else "") + src
            s2 = _insert_before_last(s, "}", ins)
        else:
            s2 = "{"+src+"}"
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

def op_splice_arrays(buf, add_buf, max_size, rng=None, **kw):
    """다른 시드(add_buf)의 배열 요소 일부를 현재 배열에 합침/셔플"""
    try:
        s = bytes(buf).decode("utf-8", errors="ignore")
        if not add_buf:
            return _clip(bytearray(buf), max_size)
        t = bytes(add_buf).decode("utf-8", errors="ignore")
        src = _extract_between(t, "[", "]")
        if src is None:
            return _clip(bytearray(buf), max_size)
        if "]" in s:
            ins = ("," if s.rfind("[") < s.rfind("]") - 1 else "") + src
            s2 = _insert_before_last(s, "]", ins)
        else:
            s2 = "["+src+"]"
        return _clip(bytearray(s2.encode("utf-8", errors="ignore")), max_size)
    except Exception:
        return _clip(bytearray(buf), max_size)

# OPS 확장 (기존 0,1,2 인덱스 보존!)
OPS += [
    op_fix_basic,
    op_rare_token,
    op_long_string,
    op_deep_nest,
    op_utf8_edge,
    op_dup_keys,
    op_add_field,
    op_delete_field,
    op_splice_objects,
    op_splice_arrays,
]

__all__ = [
    "OPS",
    "op_nop", "op_flip_bool", "op_num_boundary",
    "op_fix_basic", "op_rare_token", "op_long_string", "op_deep_nest", "op_utf8_edge",
    "op_dup_keys", "op_add_field", "op_delete_field", "op_splice_objects", "op_splice_arrays",
]
