#!/usr/bin/env bash
set -euo pipefail

# 공통
: "${AFLBIN:?need AFLBIN}"; : "${SEEDS:?}"; : "${DICT:?}"; : "${TGT:?}"
: "${OUT_ROOT:?}"; : "${DUR:?}"; : "${PY311_SP:?}"

mkdir -p "$OUT_ROOT"

# 각 out 디렉터리
BASE="$OUT_ROOT/base_default"      # 파이썬 변이기 없음
MINI="$OUT_ROOT/min_adapt"         # 초미니 변이기
REAL="$OUT_ROOT/json_adapt"        # 실제 변이기

# 코어 핀: 시스템에 맞게 코어 번호 조정(여기선 0,1,2)
CPU0=0; CPU1=1; CPU2=2

# 공통 옵션
COMMON_OPTS="-i $SEEDS -x $DICT -m none -t 200 -V $DUR -- $TGT"
# 노이즈 줄이기 (선택): 주파수 스케일링 경고 무시
export AFL_SKIP_CPUFREQ=1
# AFL 자체 코어 바인딩 비활성화: 우리가 taskset으로 핀 고정
export AFL_NO_AFFINITY=1

# 1) 베이스라인: 파이썬 변이기 없음
mkdir -p "$BASE"
taskset -c $CPU0 env -u AFL_PYTHON_MODULE \
AFL_SEED=1 \
"$AFLBIN" -o "$BASE" $COMMON_OPTS >"$BASE/run.log" 2>&1 & P1=$!

# 2) 미니 변이기
mkdir -p "$MINI"
taskset -c $CPU1 \
PYTHONPATH="$PWD:$PY311_SP" \
AFL_PYTHON_MODULE=mutators.min_adapt \
AFL_SEED=2 \
"$AFLBIN" -o "$MINI" $COMMON_OPTS >"$MINI/run.log" 2>&1 & P2=$!

# 3) 실제 변이기
mkdir -p "$REAL"
taskset -c $CPU2 \
PYTHONPATH="$PWD:$PY311_SP" \
AFL_PYTHON_MODULE=mutators.json_adapt \
AFL_SEED=3 \
"$AFLBIN" -o "$REAL" $COMMON_OPTS >"$REAL/run.log" 2>&1 & P3=$!

echo "[*] spawned:"
echo "  base      : $BASE (pid $P1, cpu $CPU0)"
echo "  min_adapt : $MINI (pid $P2, cpu $CPU1)"
echo "  json_adapt: $REAL (pid $P3, cpu $CPU2)"

wait $P1 $P2 $P3 || true
echo "[+] all done. outputs in: $OUT_ROOT"
