#!/usr/bin/env bash
# RAG-Fuzz end-to-end runner
# 수집(CPE/CVE/설명) → 사전/시드 생성 → cmin → AFL++ 실행 → 결과 요약
# 사용: tools/run_all.sh -b ./targets/json/jsonc_asan [-t tools/targets.txt] [-o out] [-j 2] [-d 3600]

set -euo pipefail

### ───── 설정값/인자 ─────────────────────────────────────────────────────────
TARGETS_FILE="tools/targets.txt"
OUT_ROOT="out"
JOBS=1               # 병렬 워커 수(-S)
DURATION=1800        # 각 워커 실행 초(sec)
BIN=""               # 필수: 타깃 바이너리
RAG_CONFIG="${HOME}/.config/ragfuzz/config.toml"

UA="Mozilla/5.0 (ragfuzz)"
API_CVE="https://services.nvd.nist.gov/rest/json/cves/2.0"
API_CPE="https://services.nvd.nist.gov/rest/json/cpes/2.0"

# 추가 환경 옵션(있으면 자동 사용)
DICT_OVERRIDE="${DICT_OVERRIDE:-}"   # 외부 dict 파일 강제 사용(비우면 자동 생성)
RAG_SKIP="${RAG_SKIP:-}"             # "1"이면 RAG 시드 생성 생략
CMPLOG_BIN="${CMPLOG_BIN:-}"         # cmplog 보조 타깃 경로(있으면 슬레이브 추가)
NO_DICT="${NO_DICT:-}"               # "1"이면 -x 사전 사용 안함
NO_MUT="${NO_MUT:-}"                 # "1"이면 Python mutator 비활성화

usage() {
  echo "Usage: $0 -b <bin> [-t targets.txt] [-o out] [-j jobs] [-d seconds]"
  exit 1
}

while getopts ":b:t:o:j:d:" opt; do
  case "$opt" in
    b) BIN="$OPTARG" ;;
    t) TARGETS_FILE="$OPTARG" ;;
    o) OUT_ROOT="$OPTARG" ;;
    j) JOBS="$OPTARG" ;;
    d) DURATION="$OPTARG" ;;
    *) usage ;;
  esac
done

[ -n "$BIN" ] || usage

# 도구 점검
for tool in curl jq rg afl-fuzz afl-cmin python3 timeout; do
  command -v "$tool" >/dev/null || { echo "need $tool"; exit 1; }
done

# 타임스탬프/경로
DATE_TAG="$(date -u +%Y%m%d_%H%M%S)"
RUN_DIR="${OUT_ROOT}/exp_${DATE_TAG}"
DICT_DIR="corpus/dict"
SEED_DIR="corpus/seed_all"
MIN_DIR="corpus/min"

mkdir -p tools "${DICT_DIR}" "${SEED_DIR}" details "${RUN_DIR}"

echo "[i] run dir      : ${RUN_DIR}"
echo "[i] targets file : ${TARGETS_FILE}"
echo "[i] binary       : ${BIN}"

### ───── 편의/안정 환경 ──────────────────────────────────────────────────────
# CPU scaling 경고 억제, affinity 대기 단축
export AFL_SKIP_CPUFREQ=1
export AFL_NO_AFFINITY=1

### ───── 유틸 함수 ───────────────────────────────────────────────────────────
curl_json() {
  # curl_json <URL> [--get ...]
  local hdr=(-H "Accept: application/json" -H "User-Agent: $UA")
  if [ -n "${NVD_API_KEY:-}" ]; then hdr+=(-H "apiKey: ${NVD_API_KEY}"); fi
  curl -sS "${hdr[@]}" "$@"
}

smoke_target() {
  # stdin에서 '{}' 입력 받고 3초 내 반환되는지 간단 체크
  chmod +x "$BIN" 2>/dev/null || true
  if ! printf '{}\n' | timeout 3s "$BIN" >/dev/null 2>&1; then
    echo "[!] target smoke test failed — ensure the binary reads from stdin and returns quickly"
    exit 1
  fi
  echo "[i] target smoke test: OK"
}

fetch_cpes() {
  local out="cpe_names.txt"
  : > "$out"
  while read -r kw || [[ -n "${kw-}" ]]; do
    [ -n "$kw" ] || continue
    curl_json --get "$API_CPE" \
      --data-urlencode "keywordSearch=$kw" \
      --data-urlencode "resultsPerPage=2000" \
    | jq -r '.products[]?.cpe.cpeName'
    sleep 0.6
  done < "$TARGETS_FILE" | sort -u -o "$out"
  echo "[i] CPE names: $(wc -l < "$out")"
}

filter_cpes() {
  awk -F: 'tolower($5) ~ /^(rapidjson|json-c|yajl|simdjson|jq|jansson)$/' \
    cpe_names.txt | sort -u > cpe_names.filtered.txt
  echo "[i] filtered CPEs: $(wc -l < cpe_names.filtered.txt)"
}

fetch_cves_by_cpe() {
  : > cve_ids.txt
  while read -r CPE || [[ -n "${CPE-}" ]]; do
    [ -n "$CPE" ] || continue
    echo "[*] CPE -> CVE: $CPE" >&2
    curl_json --get "$API_CVE" \
      --data-urlencode "cpeName=$CPE" \
      --data-urlencode "noRejected=true" \
      --data-urlencode "resultsPerPage=2000" \
    | jq -r '.vulnerabilities[]?.cve.id'
    sleep 0.6
  done < cpe_names.filtered.txt | sort -u -o cve_ids.txt
  echo "[i] CVE IDs (CPE-based): $(wc -l < cve_ids.txt)"
}

keyword_backfill() {
  local PUB_START="2010-01-01T00:00:00.000Z"
  local PUB_END; PUB_END="$(date -u +'%Y-%m-%dT%H:%M:%S.000Z')"
  while read -r kw || [[ -n "${kw-}" ]]; do
    [ -n "$kw" ] || continue
    for KW in "$kw" "$(tr '[:lower:]' '[:upper:]' <<< "$kw")" \
               "$(tr '[:lower:]' '[:upper:]' <<< "${kw:0:1}")${kw:1}"; do
      echo "[*] keywordSearch: $KW" >&2
      curl_json --get "$API_CVE" \
        --data-urlencode "keywordSearch=$KW" \
        --data-urlencode "pubStartDate=$PUB_START" \
        --data-urlencode "pubEndDate=$PUB_END" \
        --data-urlencode "noRejected=true" \
        --data-urlencode "resultsPerPage=2000" \
      | jq -r '.vulnerabilities[]?.cve.id'
      sleep 0.6
    done
  done < "$TARGETS_FILE" >> cve_ids.txt || true
  # RapidJSON 최근 CVE 힌트(중복은 정렬에서 제거)
  printf '%s\n' CVE-2024-38517 CVE-2024-39684 >> cve_ids.txt
  sort -u cve_ids.txt -o cve_ids.txt
  echo "[i] CVE IDs (CPE+keyword): $(wc -l < cve_ids.txt)"
}

fetch_details() {
  mkdir -p details
  while read -r ID || [[ -n "${ID-}" ]]; do
    [ -n "$ID" ] || continue
    echo "[*] nvd $ID"
    curl_json --get "$API_CVE" --data-urlencode "cveId=$ID" \
    | jq -r '.vulnerabilities[0].cve.descriptions[]?.value' \
    | awk 'NF' > "details/${ID}.txt"
    sleep 0.2
  done < cve_ids.txt
}

build_dicts() {
  # override 있으면 그대로 사용(동일 파일일 때 ln 에러 방지: cp -f)
  if [ -n "$DICT_OVERRIDE" ] && [ -f "$DICT_OVERRIDE" ]; then
    mkdir -p "${DICT_DIR}"
    cp -f -- "$DICT_OVERRIDE" "${DICT_DIR}/combined.dict"
    echo "[i] dict override: $DICT_OVERRIDE"
    echo "[i] dict lines: $(wc -l < "${DICT_DIR}/combined.dict")"
    return
  fi

  # 자동 키/숫자 후보
  rg -iNo '"[a-z0-9_\-$:.]+"' details \
    | sed -E 's/.*:|"(.*)"/\1/' \
    | sort -u | head -n 200 > "${DICT_DIR}/auto_from_cve_keys.dict" || true

  rg -oN '\b-?[0-9]{1,19}\b' details \
    | sort -u | head -n 200 > "${DICT_DIR}/auto_from_cve_nums.dict" || true

  # 비어 있으면 기본값
  if [ ! -s "${DICT_DIR}/auto_from_cve_keys.dict" ]; then
    cat > "${DICT_DIR}/auto_from_cve_keys.dict" <<'EOF'
"$schema"
"__proto__"
"constructor"
"NaN"
"Infinity"
"-Infinity"
"id"
"size"
"count"
"type"
"payload"
"flags"
"UTF-8"
"UTF-16"
"UTF-32"
"BOM"
EOF
  fi
  if [ ! -s "${DICT_DIR}/auto_from_cve_nums.dict" ]; then
    cat > "${DICT_DIR}/auto_from_cve_nums.dict" <<'EOF'
0
-1
1
2147483647
-2147483648
4294967295
9223372036854775807
-9223372036854775808
9007199254740991
1e308
-1e308
EOF
  fi

  # 병합
  cat \
    "${DICT_DIR}/manual.dict" \
    "${DICT_DIR}/auto.dict" \
    "${DICT_DIR}/auto_from_cve_keys.dict" \
    "${DICT_DIR}/auto_from_cve_nums.dict" \
    2>/dev/null | sort -u > "${DICT_DIR}/combined.dict"

  dict_sanitize "${DICT_DIR}/combined.dict"
  echo "[i] dict lines: $(wc -l < "${DICT_DIR}/combined.dict")"
}

dict_sanitize() {
  # 사용: dict_sanitize <path>
  local f="$1"
  cp "$f" "${f}.bak"
  # CR/BOM/비인쇄 제거 + trim + 빈줄 제거
  awk '1' "$f" \
  | LC_ALL=C sed 's/\r$//' \
  | perl -pe 's/^\xEF\xBB\xBF//' \
  | perl -pe 's/[^\x20-\x7E\n]//g' \
  | sed -E 's/^[[:space:]]+|[[:space:]]+$//' \
  | grep -v '^[[:space:]]*$' > "${f}.clean"

  # \xNN이 아닌 역슬래시는 \\ 로 이스케이프
  perl -0777 -pe 's/\\(?!x[0-9A-Fa-f]{2})/\\\\/g' "${f}.clean" > "${f}.clean2"

  # name="value" 또는 "value" 형식만 허용; 나머지는 "..."로 감쌈
  awk 'BEGIN{q="\""}
    /^[[:space:]]*[A-Za-z0-9_]+="(\\.|[^"]*)"[[:space:]]*$/ {print; next}
    /^[[:space:]]*"(\\.|[^"]*)"[[:space:]]*$/ {print; next}
    {print q $0 q}' "${f}.clean2" > "${f}"
  rm -f "${f}.clean" "${f}.clean2"
}

seed_gen() {
  mkdir -p "${SEED_DIR}"
  # 기존 시드 합치기(있으면)
  rsync -a corpus/json_seeds/ "${SEED_DIR}/" 2>/dev/null || true

  # RAG 시드 생성 (옵션: 파일 존재만 체크)
  if [ -z "$RAG_SKIP" ] && [ -f tools/rag_seedgen.py ]; then
    python3 tools/rag_seedgen.py \
      --bin "${BIN}" \
      --config "${RAG_CONFIG}" \
      --outs "${RUN_DIR}" \
      -n 100 || true
    rsync -a corpus/generated/ "${SEED_DIR}/" 2>/dev/null || true
  else
    echo "[i] skip RAG seeds"
  fi
}

cmin() {
  rm -rf "${MIN_DIR}" && mkdir -p "${MIN_DIR}"
  afl-cmin -i "${SEED_DIR}" -o "${MIN_DIR}" -- "${BIN}"
}

fuzz_run() {
  unset AFL_OUT_DIR
  export PYTHONPATH="$PWD"

  # Python mutator: 기본 on, NO_MUT=1이면 off
  if [ -z "$NO_MUT" ]; then
    : "${AFL_PYTHON_MODULE:=mutators.json_adapt}"
    export AFL_PYTHON_MODULE
  else
    unset AFL_PYTHON_MODULE
  fi

  local outdir="${RUN_DIR}/afl"
  mkdir -p "$outdir"

  # 공통 인자 구성
  local COMMON_ARGS=()
  COMMON_ARGS+=(-i "${MIN_DIR}" -o "${outdir}" -m none -t 200)
  if [ -z "$NO_DICT" ]; then
    COMMON_ARGS+=(-x "${DICT_DIR}/combined.dict")
  fi
  COMMON_ARGS+=(-- "${BIN}")

  # 마스터 1
  timeout --preserve-status "${DURATION}" \
    afl-fuzz -M m "${COMMON_ARGS[@]}" >"${outdir}/m.log" 2>&1 &

  # 슬레이브 JOBS-1
  local n=$((JOBS-1))
  for i in $(seq 1 "$n"); do
    timeout --preserve-status "${DURATION}" \
      afl-fuzz -S "s${i}" "${COMMON_ARGS[@]}" >"${outdir}/s${i}.log" 2>&1 &
  done

  # cmplog 보조 슬레이브
  if [ -n "$CMPLOG_BIN" ] && [ -x "$CMPLOG_BIN" ]; then
    timeout --preserve-status "${DURATION}" \
      afl-fuzz -S "s_cmp" -c "${CMPLOG_BIN}" "${COMMON_ARGS[@]}" >"${outdir}/s_cmp.log" 2>&1 &
    echo "[i] cmplog slave added: $CMPLOG_BIN"
  fi

  echo "[i] fuzzing launched: ${JOBS}$([ -n "$CMPLOG_BIN" ] && echo "+1(cmplog)") job(s), duration=${DURATION}s"
  wait || true
}

summarize() {
  echo "[i] afl-whatsup:"
  afl-whatsup "${RUN_DIR}/afl" || true

  # 집계 (eval.py가 있으면 상세, 없으면 간단 요약)
  if [ -f tools/eval.py ]; then
    python3 tools/eval.py --out "${RUN_DIR}/afl" --save "${RUN_DIR}/summary.csv" \
      --png "${RUN_DIR}/summary.png" || true
    echo "[i] saved CSV: ${RUN_DIR}/summary.csv"
    echo "[i] saved PNG: ${RUN_DIR}/summary.png"
  else
    echo "instance,paths_total,execs_done,unique_crashes,last_update" > "${RUN_DIR}/summary.csv"
    for d in "${RUN_DIR}"/afl/*; do
      [ -d "$d" ] || continue
      s="${d}/fuzzer_stats"
      if [ -f "$s" ]; then
        printf "%s,%s,%s,%s,%s\n" \
          "$(basename "$d")" \
          "$(grep -m1 -E 'paths_total *:' "$s" | awk '{print $3}')" \
          "$(grep -m1 -E 'execs_done *:'  "$s" | awk '{print $3}')" \
          "$(grep -m1 -E 'unique_crashes *:' "$s" | awk '{print $3}')" \
          "$(grep -m1 -E 'last_update *:'   "$s" | awk '{print $3}')" \
          >> "${RUN_DIR}/summary.csv"
      fi
    done
    echo "[i] saved CSV: ${RUN_DIR}/summary.csv"
  fi
}

### ───── 파이프라인 실행 ─────────────────────────────────────────────────────
[ -f "$TARGETS_FILE" ] || { echo "targets file not found: $TARGETS_FILE"; exit 1; }

# API 키 스모크(선택적, 지정 시)
if [ -n "${NVD_API_KEY:-}" ]; then
  curl_json --get "$API_CVE" --data-urlencode "cveId=CVE-2024-26049" \
  | jq -r '.vulnerabilities[0].cve.id' >/dev/null || echo "[w] NVD API probe failed (continuing)"
else
  echo "[w] NVD_API_KEY not set — keyword/CPE 수집 성공률이 낮을 수 있음"
fi

# 타깃 스모크
smoke_target

# 파이프라인
fetch_cpes
filter_cpes
fetch_cves_by_cpe
keyword_backfill
fetch_details
build_dicts
seed_gen
cmin
fuzz_run
summarize
