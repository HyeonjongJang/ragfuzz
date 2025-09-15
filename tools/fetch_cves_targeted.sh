#!/usr/bin/env bash
set -euo pipefail

API="https://services.nvd.nist.gov/rest/json/cves/2.0"
HDR=(-H "Accept: application/json" -H "apiKey: ${NVD_API_KEY:-}" -H "User-Agent: ragfuzz/1.0")
OUT="cve_ids.txt"
: > "$OUT"

# 1) CPE로 잘 잡히는 라이브러리들
CPEs=(
  "cpe:2.3:a:json-c_project:json-c:*:*:*:*:*:*:*:*"
  "cpe:2.3:a:lloyd:yajl:*:*:*:*:*:*:*:*"
  "cpe:2.3:a:simdjson:simdjson:*:*:*:*:*:*:*:*"
  "cpe:2.3:a:stedolan:jq:*:*:*:*:*:*:*:*"
  "cpe:2.3:a:akheron:jansson:*:*:*:*:*:*:*:*"
)

for CPE in "${CPEs[@]}"; do
  echo "[*] CPE -> CVE: $CPE" >&2
  curl -sS "${HDR[@]}" --get "$API" \
    --data-urlencode "cpeName=$CPE" \
    --data-urlencode "noRejected=true" \
    --data-urlencode "resultsPerPage=2000" \
  | jq -r '.vulnerabilities[]?.cve.id'
  sleep 0.6
done >> "$OUT"

# 2) RapidJSON은 CPE 매핑이 빈약 → 키워드+기간으로 조회 (대소문자 변형도 시도)
for KW in "RapidJSON" "rapidjson" "Tencent RapidJSON"; do
  echo "[*] KW -> CVE: $KW" >&2
  curl -sS "${HDR[@]}" --get "$API" \
    --data-urlencode "keywordSearch=$KW" \
    --data-urlencode "noRejected=true" \
    --data-urlencode "pubStartDate=2010-01-01T00:00:00.000Z" \
    --data-urlencode "pubEndDate=2025-12-31T23:59:59.000Z" \
    --data-urlencode "resultsPerPage=2000" \
  | jq -r '.vulnerabilities[]?.cve.id'
  sleep 0.6
done >> "$OUT"

# 3) 그래도 누락되면 확정된 RapidJSON CVE를 보강(중복은 아래 sort -u에서 제거)
printf '%s\n' \
  CVE-2024-38517 \
  CVE-2024-39684 \
>> "$OUT"

sort -u "$OUT" -o "$OUT"
echo "[ok] wrote $(wc -l < "$OUT") CVE IDs to $OUT"
