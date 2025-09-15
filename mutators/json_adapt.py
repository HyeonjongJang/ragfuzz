# mutators/json_adapt.py
# Robust Python mutator for AFL++ (supports both Python-only API: init/fuzz
# and afl_custom_* aliases). All exceptions are swallowed to never kill afl-fuzz.

import os, json, random
from typing import Optional, List
from .sched_ema import EMAScheduler
from .json_ops import OPS

# ── globals ──────────────────────────────────────────────────────────────────
_RNG = random.Random()
_SCHED = EMAScheduler(n_ops=len(OPS), lam=0.2, tau=0.8, eps=0.02)
_last_op: Optional[int] = None

# For simple phase control based on JSON parse rate (best-effort, never throws)
_parse_ok = 0
_parse_all = 0


# ── helpers ──────────────────────────────────────────────────────────────────
def _clip(ba: bytearray, max_size: int) -> bytearray:
    try:
        if len(ba) > max_size:
            del ba[max_size:]
    except Exception:
        pass
    return ba


def _safe_json_loads(b: bytes | bytearray) -> bool:
    try:
        json.loads(b)
        return True
    except Exception:
        return False


def _allowed_ops() -> List[int]:
    # Simple curriculum: widen operator set as parse rate improves
    try:
        rate = (_parse_ok / _parse_all) if _parse_all > 0 else 0.0
    except Exception:
        rate = 0.0

    if rate >= 0.90:
        return list(range(len(OPS)))   # Phase C: all ops
    elif rate >= 0.50:
        return [0, 1, 2]               # Phase B: moderate
    else:
        return [0, 1]                  # Phase A: safe core


# ── AFL++ "afl_custom_*" (C mutator parity) ──────────────────────────────────
def afl_custom_init(seed: int | None):
    try:
        if seed is not None:
            _RNG.seed(int(seed))
    except Exception:
        pass
    return 0


def afl_custom_deinit():
    return 0


def afl_custom_fuzz(buf, add_buf, max_size):
    global _last_op, _parse_ok, _parse_all
    try:
        data = bytearray(buf) if not isinstance(buf, bytearray) else buf

        allowed = _allowed_ops()
        if not allowed:
            allowed = [0]

        op_idx = _SCHED.pick(allowed=allowed)
        if not isinstance(op_idx, int) or not (0 <= op_idx < len(OPS)):
            op_idx = allowed[0]
        _last_op = op_idx

        # Run the operator; never let exceptions bubble out
        try:
            out = OPS[op_idx](data, add_buf, max_size, rng=_RNG)
            if not isinstance(out, (bytes, bytearray)):
                out = data
        except Exception:
            out = data

        out = _clip(bytearray(out), int(max_size))

        # Update parse stats (best-effort only)
        try:
            _parse_all += 1
            if _safe_json_loads(out):
                _parse_ok += 1
        except Exception:
            pass

        return bytes(out)

    except Exception:
        # Last resort: return original buffer or minimal valid JSON
        try:
            return bytes(bytearray(buf))
        except Exception:
            return b"{}"


def afl_custom_post_process(buf):
    return post_process(buf)


def afl_custom_queue_new_entry(filename, orig_filename):
    queue_new_entry(filename, orig_filename)


# ── Python-only mutator API expected by AFL++ (init/fuzz/deinit/…) ───────────
def init(seed=None):
    # Some afl++ builds call without an argument; keep it permissive
    try:
        return afl_custom_init(seed)
    except TypeError:
        return afl_custom_init(None)


def deinit():
    return afl_custom_deinit()


def fuzz(buf, add_buf, max_size):
    return afl_custom_fuzz(buf, add_buf, max_size)


def post_process(buf):
    # No-op post-process by default (keep wire compatibility)
    return buf


def queue_new_entry(filename: str, *rest) -> None:
    # Reward the last operator when afl adds a new queue entry
    try:
        if isinstance(_last_op, int):
            _SCHED.reward_update(_last_op, d_cov=0.0, uniq_crash=False, new_path=True)
    except Exception:
        pass


def new_crash(filename: str, *rest) -> None:
    # Extra credit if a crash was found
    try:
        if isinstance(_last_op, int):
            _SCHED.reward_update(_last_op, d_cov=0.0, uniq_crash=True, new_path=True)
    except Exception:
        pass
