# mutators/json_adapt.py
import time
import json
import os
import random
import traceback
from collections import deque
from typing import List, Optional

from .sched_ema import EMAScheduler
from .json_ops import OPS  # 연산자 함수 리스트만 필요


# --- 이름 -> 인덱스 자동 매핑 (json_ops 수정 없이 동작) ---
_OP_INDEX = {getattr(f, "__name__", f"op_{i}"): i for i, f in enumerate(OPS)}

def _idx(name: str) -> Optional[int]:
    i = _OP_INDEX.get(name)
    if isinstance(i, int) and 0 <= i < len(OPS):
        return i
    return None

def _sanitize_idx_list(lst: List[int]) -> List[int]:
    """허용 인덱스 목록 방어(범위 밖 제거, 빈 리스트면 0만 허용)."""
    out = []
    for v in lst:
        if isinstance(v, int) and 0 <= v < len(OPS):
            out.append(v)
    if not out:
        out = [0]  # 최소 0번(op_nop 가정) 허용
    return out


# === 전역 상태 ===
_PHASE        = "A"     # A -> B -> C
_parse_ok     = 0
_parse_all    = 0
_last_op      = 0
_last_fuzz_ts = 0.0

# plateau 판단용: 최근 새 경로 timestamp 저장
_newpath_ts = deque(maxlen=256)

# 파라미터
PHASE_PARSE_TARGET = 0.90
PLATEAU_WINDOW_SEC = 60 * 3   # 최근 3분
PLATEAU_MIN_NEW    = 3        # 이 기간 동안 신규 경로가 k 미만이면 plateau

# 스케줄러는 OPS 길이에 맞춰 초기화
_SCHED = EMAScheduler(n_ops=len(OPS), lam=0.2, tau=0.8, eps=0.02)

# 사이드카 제어파일 경로
_CTL_PATH: Optional[str] = None


def _phase_ops() -> List[int]:
    """현재 페이즈에 허용할 연산자 인덱스 목록(이름 기반 -> 인덱스 -> 정제)."""
    if _PHASE == "A":
        cand_names = ["op_nop", "op_fix_basic", "op_flip_bool"]
    elif _PHASE == "B":
        cand_names = ["op_nop", "op_fix_basic", "op_num_boundary", "op_rare_token"]
    else:  # "C"
        return list(range(len(OPS)))

    cand = [_idx(n) for n in cand_names]
    cand = [i for i in cand if i is not None]
    return _sanitize_idx_list(cand)


def _maybe_advance_phase() -> None:
    """내부 지표(파싱률/plateau)로 페이즈 전이."""
    global _PHASE
    # 파싱 성공률
    parse_rate = (_parse_ok / _parse_all) if _parse_all else 0.0

    # plateau 감지
    now = time.time()
    new_recent = [t for t in _newpath_ts if now - t <= PLATEAU_WINDOW_SEC]
    plateau = (len(new_recent) < PLATEAU_MIN_NEW)

    # 전이 규칙
    if _PHASE == "A":
        if parse_rate >= PHASE_PARSE_TARGET:
            _PHASE = "B"
            _SCHED.reset_scores()
    elif _PHASE == "B":
        if plateau:
            _PHASE = "C"
            _SCHED.reset_scores()
    else:  # C
        if plateau:
            _SCHED.reset_scores()


def _read_ctl() -> None:
    """tools/phase_ctl.py가 쓰는 phase_ctl.json을 읽어 외부 plateau 신호에 반응."""
    global _PHASE
    if not _CTL_PATH or not os.path.exists(_CTL_PATH):
        return
    try:
        ctl = json.loads(open(_CTL_PATH, "r", encoding="utf-8").read() or "{}")
        if ctl.get("plateau"):
            if _PHASE == "B":
                _PHASE = "C"
                _SCHED.reset_scores()
            elif _PHASE == "C":
                _SCHED.reset_scores()
            # A에서는 내부 파싱률로만 전이
    except Exception:
        # 제어파일 파싱 에러 등은 무시(안전 우선)
        pass


# === AFL++ 커스텀 뮤테이터 표준 훅들 ===

def init(seed: int) -> int:
    random.seed(seed)
    # 사이드카 제어파일 경로 설정 (AFL_OUT_DIR/default/phase_ctl.json)
    out_dir = os.getenv("AFL_OUT_DIR")
    if out_dir:
        global _CTL_PATH
        _CTL_PATH = os.path.join(out_dir, "default", "phase_ctl.json")
    return 0


def fuzz(data: bytearray, add_buf: bytes, max_size: int) -> bytearray:
    """반드시 bytearray 반환 & max_size 준수 & 예외는 원본 반환."""
    global _last_op, _parse_ok, _parse_all, _last_fuzz_ts
    try:
        allowed = _sanitize_idx_list(_phase_ops())
        _last_op = _SCHED.pick(allowed)

        out = OPS[_last_op](data, add_buf, max_size)

        # 타입/길이 방어
        if isinstance(out, bytes):
            out = bytearray(out)
        elif not isinstance(out, bytearray):
            out = bytearray(out)
        if len(out) > max_size:
            out = out[:max_size]

        # 파싱 성공률 추적 (빠른 json.loads)
        _parse_all += 1
        try:
            json.loads(out.decode("utf-8", "ignore"))
            _parse_ok += 1
        except Exception:
            pass

        _last_fuzz_ts = time.time()

        # 주기적으로 페이즈 전이 + 사이드카 제어파일 체크
        if (_parse_all & 0x7F) == 0:  # 128회마다
            _maybe_advance_phase()
            _read_ctl()

        return out
    except Exception:
        # 어떤 경우에도 크래시는 내지 않게
        traceback.print_exc()
        if (_parse_all & 0xFF) == 0:  # 256회마다 한 번
            print(f"[phase]{_PHASE} parse={_parse_ok}/{_parse_all}")
        return bytearray(data[:max_size])


def deinit() -> None:
    pass


# === AFL++ 이벤트 훅들 ===

def queue_new_entry(filename: str, *rest) -> None:
    """새 큐 item이 생기면 'novel path'로 간주해 보상 및 plateau 통계 업데이트."""
    try:
        _SCHED.reward_update(_last_op, d_cov=0.0, uniq_crash=False, new_path=True)
        _newpath_ts.append(time.time())
    except Exception:
        pass


def new_crash(filename: str, *rest) -> None:
    try:
        _SCHED.reward_update(_last_op, d_cov=0.0, uniq_crash=True, new_path=True)
    except Exception:
        pass
