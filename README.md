# RAG-Guided AFL++ JSON 퍼징 — 실행 가이드

_최종 업데이트: 2025-09-15 (KST)_

레포의 **현재 폴더/파일 구조**와 최신 적응 변이기 스택(EMA 스케줄러 + A/B/C 커리큘럼 + plateau 사이드카(선택) + LLM 시드/사전)을 기준으로 재현 가능한 실행 가이드입니다.

## 레포 구조(핵심 경로)

```
ragfuzz/
  corpus/
  engine/
  mutators/
  out/
  rag/                 # (있을 경우)
  reports/
  scripts/
  targets/
  tools/
  triage/
  README.md
```

- `mutators/` — 적응 변이기와 연산자들 (`json_adapt.py`, `json_ops.py`, `sched_ema.py`, 실험용 `softmax_mutator.py`)
- `tools/` — 유틸(LLM 시드/사전 `rag_seedgen.py`, plateau 사이드카 `phase_ctl.py`, 통계 수집 `collect.py`)
- `targets/json/json_asan` — JSON 타깃 바이너리(ASAN). 없으면 **2‑4 타깃 빌드** 참고
- `corpus/` — 초기 시드 `json_seeds/`, 사전 `dict/json.dict`, 실행 중 생성물 `generated/`, `seed_all/`
- `scripts/` — 원커맨드 스크립트가 있다면 활용
- `triage/`, `reports/` — (선택) 사후 분석 산출물

> 위 구조와 일부 명령은 레포의 README에도 기재되어 있습니다.

## 0) 요구 사항

- **OS**: Ubuntu 22.04 / WSL2
- **Python**: 3.11 권장 (conda/venv)
- **AFL++**: 소스 빌드 후 `PATH` 등록
- (선택) OpenAI 호환 키(LLM 시드/사전)

시스템 패키지:
```bash
sudo apt-get update
sudo apt-get install -y git build-essential clang lld cmake python3-pip python3-venv jq rsync pkg-config
```

## 1) 파이썬 환경 & AFL++

### 1‑1) 파이썬 환경
Conda:
```bash
conda create -n ragfuzz python=3.11 -y
conda activate ragfuzz
```
또는 venv:
```bash
python3 -m venv ~/.venvs/ragfuzz
source ~/.venvs/ragfuzz/bin/activate
python -V
pip install --upgrade pip
```

패키지:
```bash
pip install "openai>=1.40.0" tomli tomlkit
```

### 1‑2) AFL++
```bash
cd ~
git clone https://github.com/AFLplusplus/AFLplusplus.git
cd AFLplusplus
make distrib -j$(nproc)
echo 'export PATH="$HOME/AFLplusplus:$PATH"' >> ~/.bashrc
source ~/.bashrc
which afl-fuzz
```

### 1‑3) 타깃 빌드(없을 때)
```bash
cd ~/ragfuzz/targets/json
clang -O2 -g -fsanitize=address -fno-omit-frame-pointer -o json_asan json_target.c
```

## 2) 스모크 테스트: 변이기 임포트 + 10초 퍼징

```bash
cd ~/ragfuzz
export PYTHONPATH="$PWD"

python - <<'PY'
import importlib
m = importlib.import_module('mutators.json_adapt')
buf = bytearray(b'a')
out = m.fuzz(buf, b'', 1024)
print(type(out), len(out))
PY

export AFL_PYTHON_MODULE=mutators.json_adapt
env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1   afl-fuzz -i corpus/json_seeds -o out/smoke   -x corpus/dict/json.dict -m none -t 200 -V 10 --   ./targets/json/json_asan
```

## 3) (선택) LLM 시드/사전 생성 + 병합

설정:
```bash
mkdir -p ~/.secrets ~/.config/ragfuzz
printf 'sk-실제키\n' > ~/.secrets/openai.key
chmod 700 ~/.secrets; chmod 600 ~/.secrets/openai.key
cat > ~/.config/ragfuzz/config.toml <<'TOML'
[llm]
provider    = "openai"
model       = "gpt-4o-mini"
temperature = 1.1
api_key_file = "/home/USER/.secrets/openai.key"  # USER 교체
TOML
```

생성 & 병합:
```bash
python3 tools/rag_seedgen.py   --bin ./targets/json/json_asan   --config ~/.config/ragfuzz/config.toml   -n 20

cat corpus/dict/json.dict corpus/dict/auto.dict | sort -u > corpus/dict/combined.dict
mkdir -p corpus/seed_all
rsync -a corpus/json_seeds/ corpus/seed_all/
rsync -a corpus/generated/  corpus/seed_all/
```

## 4) 적응 실행(EMA + 커리큘럼)

```bash
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt

env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1   afl-fuzz -i corpus/seed_all -o out/llm_10min   -x corpus/dict/combined.dict -m none -t 200 -V 600 --   ./targets/json/json_asan
```

**페이즈 규칙(현행):**  
- **A**: 기본 유효성 (예: `op_nop`, `op_flip_bool`)  
- **B**: 경계값 주입 활성화 (예: `op_num_boundary`)  
- **C**: 모든 연산자 사용  
- **전이**: A→B는 파싱률 ≥ 0.90, B→C는 plateau 시; C에서는 plateau 시 EMA 리셋

연산자 **이름 기반 매핑**으로 안전하게 동작하며, 존재하지 않는 연산자는 자동 무시됩니다.

## 5) (선택) Plateau 사이드카 → B→C

터미널 A:
```bash
python3 tools/phase_ctl.py --out out/adapt_llm_smoke --window 180 --k 3
```

터미널 B:
```bash
export AFL_OUT_DIR=out/adapt_llm_smoke
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt
env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1   afl-fuzz -i corpus/seed_all -o out/adapt_llm_smoke   -x corpus/dict/combined.dict -m none -t 200 -V 600 --   ./targets/json/json_asan
```

수동 토글:
```bash
echo '{"plateau": true}' > out/adapt_llm_smoke/default/phase_ctl.json
```

## 6) 베이스라인 vs LLM/적응 비교

**베이스라인(변이기X):**
```bash
unset AFL_PYTHON_MODULE
env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1   afl-fuzz -i corpus/json_seeds -o out/base_10min   -x corpus/dict/json.dict -m none -t 200 -V 600 --   ./targets/json/json_asan
```

**LLM + 적응:**
```bash
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt
env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1   afl-fuzz -i corpus/seed_all -o out/llm_10min   -x corpus/dict/combined.dict -m none -t 200 -V 600 --   ./targets/json/json_asan
```

통계 수집(`tools/collect.py`가 있을 때):
```bash
python3 tools/collect.py out/base_10min stats_base.csv
python3 tools/collect.py out/llm_10min  stats_llm.csv
```

핵심 지표: `edges_found`, `paths_total`, 초기 성장률, dict 히트, TTFC(있다면).

## 7) 코퍼스 최소화 & 크래시 트리아지

```bash
afl-cmin -i out/llm_10min/default/queue -o corpus/min -- ./targets/json/json_asan
afl-tmin -i crashes/id:XXXXXX -o minimized -- ./targets/json/json_asan
```

## 8) 튜닝 팁

- **EMA**: 탐색↑ `eps≈0.05–0.10`, 수렴↑ `lam≈0.1–0.2` (낮출수록 exploitation)
- **A→B 임계**: 타깃이 유효 JSON을 많이 파싱하면 0.85로 낮춰 전이 가속
- **Plateau 창**: 느린 타깃은 `window↑` 또는 `k↓`
- **LLM**: 초기 `-n 100–200`으로 커버리지 가속, `auto.dict` 성장을 확인

## 9) 비고

- `mutators/softmax_mutator.py`는 **실험용** 대체 변이기이며, 기본 경로는 `mutators/json_adapt.py`.
- `mutators/json_ops.py`에 연산자를 추가하면 이름 기반으로 즉시 반영됩니다.
- `scripts/run_all.sh`가 있다면 A/B/C 시나리오를 원커맨드로 실행할 수 있습니다(없으면 위 명령 사용).
