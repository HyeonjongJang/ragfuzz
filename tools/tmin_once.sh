set -euo pipefail
unset AFL_OUT_DIR
CR=$(ls out/jsonc_inst/crashes/id:* 2>/dev/null | head -n1 || true)
if [ -z "$CR" ]; then
  echo "No crash yet. Skip tmin."
  exit 0
fi
mkdir -p min
ASAN_OPTIONS=abort_on_error=1:detect_leaks=0:symbolize=0 \
afl-tmin -i "$CR" -o "min/$(basename "$CR").min" -- ./targets/json/jsonc_asan
echo "min/$(basename "$CR").min created."
