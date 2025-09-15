#!/usr/bin/env bash
set -euo pipefail

API="https://services.nvd.nist.gov/rest/json/cves/2.0"
UA="Mozilla/5.0 (ragfuzz)"
PER_PAGE=200
SLEEP_BETWEEN=0.6
MAX_RETRY=5

# 필요한 키워드만 우선(처음엔 라이브러리명 위주로 추천)
KWS=(
  json-c yajl rapidjson simdjson jq jansson
  "utf-8" utf8 "duplicate key" "deep recursion" "stack exhaustion"
  "number parsing" "trailing comma" "large depth"
  NaN Infinity BOM surrogate "UTF-16" "UTF-32"
  "heap overflow" "use-after-free" "integer overflow"
)

: > cve_ids.txt

nvd_call() { # args: keyword startIndex
  local kw="$1" start="$2" try=0 out code
  while :; do
    ((try++)) || true
    out=$(mktemp)
    code=$(curl -sS -w '%{http_code}' -o "$out" \
      -H "User-Agent: $UA" \
      -H "Accept: application/json" \
      -H "apiKey: ${NVD_API_KEY:-}" \
      --get "$API" \
      --data-urlencode "keywordSearch=$kw" \
      --data-urlencode "noRejected=true" \
      --data-urlencode "resultsPerPage=$PER_PAGE" \
      --data-urlencode "startIndex=$start")
    if [ "$code" = "200" ] && jq -e . >/dev/null 2>&1 <"$out"; then
      cat "$out"; rm -f "$out"; return 0
    fi
    rm -f "$out"
    if [ "$try" -ge "$MAX_RETRY" ]; then
      echo "[warn] NVD call failed ($kw, start=$start, http=$code) - giving up" >&2
      return 1
    fi
    sleep_sec=$(awk -v t="$try" 'BEGIN{print (2^(t-1))*0.7}')
    echo "[info] retry ($try/$MAX_RETRY) $kw start=$start after ${sleep_sec}s (http=$code)" >&2
    sleep "$sleep_sec"
  done
}

for KW in "${KWS[@]}"; do
  echo "[*] NVD keyword: $KW"
  first_json=$(nvd_call "$KW" 0 || true)
  if [ -z "${first_json:-}" ]; then
    echo "    -> no JSON (rate limit or none)"; continue
  fi
  total=$(jq -r '.totalResults // 0' <<<"$first_json")
  if [ "$total" -eq 0 ]; then
    echo "    -> total=0"; continue
  fi
  echo "    -> total=$total"
  jq -r '.vulnerabilities[].cve.id' <<<"$first_json" >> cve_ids.txt

  start=$PER_PAGE
  while [ "$start" -lt "$total" ]; do
    sleep "$SLEEP_BETWEEN"
    page_json=$(nvd_call "$KW" "$start" || true)
    [ -z "${page_json:-}" ] && break
    jq -r '.vulnerabilities[].cve.id' <<<"$page_json" >> cve_ids.txt
    start=$((start + PER_PAGE))
  done
done

sort -u cve_ids.txt -o cve_ids.txt
echo "[ok] CVE IDs: $(wc -l < cve_ids.txt)"
