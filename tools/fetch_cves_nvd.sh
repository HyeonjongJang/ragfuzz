#!/usr/bin/env bash
set -euo pipefail

API_VULN="https://services.nvd.nist.gov/rest/json/cves/2.0"
API_CPE="https://services.nvd.nist.gov/rest/json/cpes/2.0"
UA="Mozilla/5.0 (ragfuzz)"
PER_PAGE=2000
DELAY=1.0

# 우선 라이브러리명만(검증 편의)
KWS=("rapidjson" "json-c" "yajl" "simdjson" "jq" "jansson")

out_ids="cve_ids.txt"
: > "$out_ids"

curl_json() { curl -sS -H "Accept: application/json" -H "User-Agent: $UA" -H "apiKey: ${NVD_API_KEY:-}" "$@"; }

# 1) CPE 후보 수집
tmp_cpe=$(mktemp)
: > "$tmp_cpe"
for kw in "${KWS[@]}"; do
  echo "[*] CPE keyword: $kw"
  curl_json --get "$API_CPE" \
    --data-urlencode "keywordSearch=$kw" \
    --data-urlencode "resultsPerPage=$PER_PAGE" \
  | jq -r '.products[]?.cpe.cpeName' || true
  sleep "$DELAY"
done | sort -u > "$tmp_cpe"
echo "[*] CPE candidates: $(wc -l < "$tmp_cpe")"

# 2) CPE → CVE
while read -r CPE; do
  [ -n "$CPE" ] || continue
  echo "[*] CVEs for $CPE" >&2
  curl_json --get "$API_VULN" \
    --data-urlencode "cpeName=$CPE" \
    --data-urlencode "noRejected" \
    --data-urlencode "resultsPerPage=$PER_PAGE" \
  | jq -r '.vulnerabilities[]?.cve.id' || true
  sleep "$DELAY"
done < "$tmp_cpe" >> "$out_ids"

# 3) (보강) 설명 키워드 매칭(최근 기간)
PUB_START="2010-01-01T00:00:00.000Z"
PUB_END="$(date -u +'%Y-%m-%dT%H:%M:%S.000Z')"
for kw in "${KWS[@]}"; do
  echo "[*] DESC keyword: $kw" >&2
  curl_json --get "$API_VULN" \
    --data-urlencode "keywordSearch=$kw" \
    --data-urlencode "noRejected" \
    --data-urlencode "pubStartDate=$PUB_START" \
    --data-urlencode "pubEndDate=$PUB_END" \
    --data-urlencode "resultsPerPage=$PER_PAGE" \
  | jq -r '.vulnerabilities[]?.cve.id' || true
  sleep "$DELAY"
done >> "$out_ids"

sort -u "$out_ids" -o "$out_ids"
echo "[ok] CVE IDs: $(wc -l < "$out_ids") → $out_ids"
