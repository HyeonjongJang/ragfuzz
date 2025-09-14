# RAG-Guided Adaptive Fuzzing (AFL++) — Runbook / README

This README is a **step-by-step execution guide** to reproduce the setup and experiments for our *RAG-guided, curriculum + EMA-scheduler adaptive fuzzing* with AFL++ and a JSON target.

It is written to be **copy–paste runnable** on a fresh Ubuntu/WSL machine.

---

## 0) Requirements

- **OS**: Ubuntu 22.04 (bare metal / VM / WSL2)
- **User**: normal user (no root needed for most steps)
- **Network**: outbound access if you will use the LLM seed/dict generator
- **CPU**: the more cores, the better (multi-core fuzzing)

### System packages

```bash
sudo apt-get update
sudo apt-get install -y git build-essential clang lld cmake python3-pip python3-venv \
                        jq rsync pkg-config
```

> macOS: `brew install llvm cmake jq rsync` works similarly.

---

## 1) Get the repo & check the tree

```bash
cd ~
git clone <YOUR-RAGFUZZ-REPO-URL> ragfuzz
cd ~/ragfuzz
```

Expected structure (key files only):
```
ragfuzz/
  mutators/
    __init__.py
    json_adapt.py      # Adaptive mutator (EMA + curriculum phases A/B/C)
    json_ops.py
    sched_ema.py
  tools/
    rag_seedgen.py     # LLM/RAG seed & dict generator
    phase_ctl.py       # Sidecar for plateau detection
    collect.py         # Parse AFL++ plot_data -> CSV
  corpus/
    json_seeds/        # Initial seeds (2–3+ JSON examples)
    dict/
      json.dict        # Base dictionary
  targets/
    json/
      json_asan        # Target binary (ASAN). If missing, see 2-4.
```

---

## 2) Python env & AFL++

### 2-1) Create a Python env (conda or venv)

**Conda (recommended):**
```bash
conda create -n ragfuzz python=3.11 -y
conda activate ragfuzz
```

**OR venv:**
```bash
python3 -m venv ~/.venvs/ragfuzz
source ~/.venvs/ragfuzz/bin/activate
python -V  # 3.11.x recommended
```

### 2-2) Python packages

```bash
pip install --upgrade pip
pip install "openai>=1.40.0" tomli tomlkit
```

### 2-3) AFL++

```bash
cd ~
git clone https://github.com/AFLplusplus/AFLplusplus.git
cd AFLplusplus
make distrib -j$(nproc)
echo 'export PATH="$HOME/AFLplusplus:$PATH"' >> ~/.bashrc
source ~/.bashrc
which afl-fuzz   # e.g., /home/USER/AFLplusplus/afl-fuzz
```

### 2-4) Build target (only if missing)

If your repo already contains `targets/json/json_asan`, **skip** this section. Otherwise, compile your JSON target with ASAN and persistent mode as appropriate for your project.

> Example (pseudo):
> ```bash
> cd ~/ragfuzz/targets/json
> clang -O2 -g -fsanitize=address -fno-omit-frame-pointer \
>       -o json_asan json_target.c
> ```

---

## 3) Import the mutator (smoke test)

```bash
cd ~/ragfuzz
export PYTHONPATH="$PWD"

python - <<'PY'
import importlib
m = importlib.import_module('mutators.json_adapt')
buf = bytearray(b'{"a":1}')
out = m.fuzz(buf, b'', 1024)
print(type(out), len(out))
PY
```
You should see something like `<class 'bytearray'> 6` and **no errors**.

---

## 4) LLM configuration (optional but recommended)

You can run without LLM. However, enabling it boosts initial coverage by injecting smarter seeds & dictionary tokens.

### 4-1) Save your OpenAI key

```bash
mkdir -p ~/.secrets
printf 'sk-YOUR-REAL-API-KEY\n' > ~/.secrets/openai.key
chmod 700 ~/.secrets
chmod 600 ~/.secrets/openai.key
```

### 4-2) Create config TOML

```bash
mkdir -p ~/.config/ragfuzz
cat > ~/.config/ragfuzz/config.toml <<'TOML'
[llm]
provider    = "openai"
model       = "gpt-4o-mini"
temperature = 1.1
# base_url = "https://api.openai.com/v1"  # set this if you use a proxy/self-hosted compatible endpoint
api_key_file = "/home/USER/.secrets/openai.key"  # replace USER with your username
TOML
```

> Replace `/home/USER` with your **actual** user home (e.g., `/home/aims`).

### 4-3) Key test

```bash
python - <<'PY'
from openai import OpenAI
key = open('/home/USER/.secrets/openai.key','r',encoding='utf-8').read().strip()  # replace USER
cli = OpenAI(api_key=key)
r = cli.responses.create(model="gpt-4o-mini", input="ping")
print("OK:", bool(getattr(r, "output_text", None)))
PY
```

You should see `OK: True`.

---

## 5) Generate LLM seeds & merge dictionary (optional)

> If you skip this, keep using the stock `corpus/json_seeds` and `corpus/dict/json.dict`.

```bash
cd ~/ragfuzz

# Generate N candidates; filters: JSON-parse + mini-harness run
python3 tools/rag_seedgen.py \
  --bin ./targets/json/json_asan \
  --config ~/.config/ragfuzz/config.toml \
  -n 20

# Merge dictionaries
cat corpus/dict/json.dict corpus/dict/auto.dict | sort -u > corpus/dict/combined.dict

# Combine seeds (stock + generated)
mkdir -p corpus/seed_all
rsync -a corpus/json_seeds/ corpus/seed_all/
rsync -a corpus/generated/  corpus/seed_all/
```

**Verify:**
- New files in `corpus/generated/`
- `corpus/dict/auto.dict` created/updated
- `corpus/dict/combined.dict` exists and is non-empty

---

## 6) Quick smoke fuzz (10 seconds)

```bash
cd ~/ragfuzz
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt
find mutators -name '__pycache__' -type d -exec rm -rf {} +

env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
  afl-fuzz -i corpus/json_seeds -o out/adapt_smoke \
  -x corpus/dict/json.dict -m none -t 200 -V 10 -- \
  ./targets/json/json_asan
```

Expected: total execs increase, corpus grows, exit cleanly with `fastresume.bin`. **No segfaults**.

---

## 7) LLM seeds + adaptive scheduler run (10 minutes)

```bash
cd ~/ragfuzz
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt

env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
  afl-fuzz -i corpus/seed_all -o out/llm_10min \
  -x corpus/dict/combined.dict -m none -t 200 -V 600 -- \
  ./targets/json/json_asan
```

Watch for:
- Dictionary stage hits (not all zeros)
- `edges_found`, `paths_total` should climb faster than baseline

---

## 8) (Optional) Sidecar plateau detection → Phase B→C

**Terminal A (sidecar):**
```bash
cd ~/ragfuzz
python3 tools/phase_ctl.py --out out/adapt_llm_smoke --window 180 --k 3
# Writes out/adapt_llm_smoke/default/phase_ctl.json
```

**Terminal B (fuzzer, must set AFL_OUT_DIR):**
```bash
cd ~/ragfuzz
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt
export AFL_OUT_DIR=out/adapt_llm_smoke

env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
  afl-fuzz -i corpus/seed_all -o out/adapt_llm_smoke \
  -x corpus/dict/combined.dict -m none -t 200 -V 600 -- \
  ./targets/json/json_asan
```

**Manual toggle (quick test, no sidecar):**
```bash
echo '{"plateau": true}' > out/adapt_llm_smoke/default/phase_ctl.json
```

The mutator periodically reads this file; when plateau is true during phase B, it transitions to C and resets EMA scores.

---

## 9) Baseline vs LLM comparison

**A) Baseline (no LLM):**
```bash
unset AFL_PYTHON_MODULE
env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
  afl-fuzz -i corpus/json_seeds -o out/base_10min \
  -x corpus/dict/json.dict -m none -t 200 -V 600 -- \
  ./targets/json/json_asan
```

**B) LLM + adaptive (current):**
```bash
export PYTHONPATH="$PWD"
export AFL_PYTHON_MODULE=mutators.json_adapt
env -u LD_LIBRARY_PATH AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 \
  afl-fuzz -i corpus/seed_all -o out/llm_10min \
  -x corpus/dict/combined.dict -m none -t 200 -V 600 -- \
  ./targets/json/json_asan
```

**Collect & compare:**
```bash
python3 tools/collect.py out/base_10min stats_base.csv
python3 tools/collect.py out/llm_10min  stats_llm.csv
```
Key metrics: `edges_found`, `paths_total`, early growth rate, dictionary hits, time-to-first-crash (if any).

---

## 10) Corpus curation

```bash
# Minimize corpus
afl-cmin -i out/llm_10min/default/queue -o corpus/min -- ./targets/json/json_asan

# Minimize a specific interesting/crash case
afl-tmin -i crashes/id:XXXXX -o minimized -- ./targets/json/json_asan
```

(Optionally, add coverage-profile hashing to dedupe beyond file hashes.)

---

## 11) Multi-core fuzzing

```bash
# Master
afl-fuzz -i corpus/seed_all -o out/cluster \
  -x corpus/dict/combined.dict -M f0 -m none -t 200 -- ./targets/json/json_asan

# Slave 1
afl-fuzz -i corpus/seed_all -o out/cluster \
  -x corpus/dict/combined.dict -S s1 -m none -t 200 -- ./targets/json/json_asan

# Add more slaves (s2, s3, ...)
```

> If you want adaptive mutator on all workers: set `export AFL_PYTHON_MODULE=mutators.json_adapt` for each process.

---

## 12) Troubleshooting

- **`ModuleNotFoundError: mutators.json_adapt`**
  - `export PYTHONPATH="$PWD"`?
  - Does `mutators/__init__.py` exist? (`touch mutators/__init__.py`)

- **Dictionary stage shows zeros**
  - Verify `-x` path and that `combined.dict` is non-empty & readable.

- **Segfaults**
  - Mutator must **return `bytearray`** and respect `max_size`. Current code enforces this.

- **`IndexError` in scheduler**
  - Caused by operator index set mismatch. Current mutator sanitizes `allowed` via operator-name mapping.

- **OpenAI 401**
  - Check `~/.secrets/openai.key` content/permissions (600)
  - Check `~/.config/ragfuzz/config.toml` `api_key_file` path (username!)
  - Ensure `openai>=1.40.0`

- **Sidecar seems ignored**
  - `export AFL_OUT_DIR=<same as -o>` before running afl-fuzz
  - Check `out/.../default/phase_ctl.json` timestamp & content

- **Slow fuzzing**
  - Keep `-m none`
  - Use `env -u LD_LIBRARY_PATH` to avoid LD issues
  - Run multi-core (`-M/-S` mode)

- **`core_pattern` warning**
  - For experiments, we already set `AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1`

---

## 13) Resume / Restart

- Reusing the same `-o` directory will auto-resume from `fastresume.bin`.
- For a clean run, switch to a new `-o` directory or delete the old one.

---

## 14) Advanced tuning

- **Long C-phase runs** for crash hunting; triage & dedupe by backtrace hash.
- **Periodic RAG loop**: run `tools/rag_seedgen.py` every N minutes; merge to `combined.dict`.
- **EMA hyperparams**:
  - More exploration: `eps = 0.05~0.1`, `tau = 0.6~0.8`
  - Tighter exploitation: decrease `eps`, tweak `lam` (0.1–0.3 typical)

---

## Acknowledgements

- AFL++: https://github.com/AFLplusplus/AFLplusplus
- Thanks to the AFL++ maintainers & fuzzing community.
