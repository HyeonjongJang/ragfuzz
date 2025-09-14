#!/usr/bin/env python3
import os, json, glob, subprocess, argparse, random, time, pathlib, re, sys
from typing import List, Dict, Any, Iterable

# ---------- 설정 로딩 ----------
def _read_text_file(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8", errors="ignore").strip()

def load_llm_config(config_path: str|None) -> Dict[str, Any]:
    """
    TOML 설정(~/.config/ragfuzz/config.toml)을 읽고,
    환경변수 OPENAI_API_KEY가 있으면 api_key를 그 값으로 덮어씁니다.
    """
    cfg = {"llm": {}}
    if not config_path:
        # 기본 경로
        default = os.path.expanduser("~/.config/ragfuzz/config.toml")
        if pathlib.Path(default).exists():
            config_path = default
    if config_path:
        try:
            import tomllib  # Python 3.11+
            with open(config_path, "rb") as f:
                cfg = tomllib.load(f)
        except Exception as e:
            print(f"[rag] WARN: failed to load config {config_path}: {e}", file=sys.stderr)

    llm = cfg.get("llm", {})
    api_key = llm.get("api_key")  # 가능하면 파일로 보관 권장
    api_key_file = llm.get("api_key_file")
    if (not api_key) and api_key_file and pathlib.Path(api_key_file).exists():
        try:
            api_key = _read_text_file(api_key_file)
        except Exception as e:
            print(f"[rag] WARN: failed to read api_key_file: {e}", file=sys.stderr)

    # 환경변수 있으면 최우선
    if os.environ.get("OPENAI_API_KEY"):
        api_key = os.environ["OPENAI_API_KEY"]

    return {
        "provider":   llm.get("provider", "openai"),
        "model":      llm.get("model", "gpt-4o-mini"),
        "temperature": float(llm.get("temperature", 1.1)),
        "base_url":   llm.get("base_url"),  # 없으면 SDK 기본
        "api_key":    api_key,
    }

# ---------- 코퍼스/키 수집 ----------
def parse_ok(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False

def flatten_keys(obj, out: set):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k))
            flatten_keys(v, out)
    elif isinstance(obj, list):
        for it in obj:
            flatten_keys(it, out)

def extract_keys_from_files(files: Iterable[str], limit=500) -> List[str]:
    keys = set()
    n = 0
    for fn in files:
        if n >= limit: break
        try:
            txt = pathlib.Path(fn).read_text(errors="ignore")
            obj = json.loads(txt)
            flatten_keys(obj, keys)
            n += 1
        except Exception:
            continue
    return sorted(keys)[:128]

def gather_hints(corpus_dirs: List[str], out_dirs: List[str]) -> Dict[str, Any]:
    files = []
    for d in corpus_dirs or []:
        files += glob.glob(os.path.join(d, "*.json"))
    for out in out_dirs or []:
        q = os.path.join(out, "default", "queue", "*")
        files += glob.glob(q)
    keys = extract_keys_from_files(files, limit=500)
    return {"keys": keys}

# ---------- 하니스 빠른 검증 ----------
def fast_harness_ok(bin_path: str, data: str, timeout_ms=60) -> bool:
    try:
        p = subprocess.run(
            [bin_path],
            input=data.encode("utf-8", "ignore"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_ms / 1000.0,
            check=False,
        )
        # 신호로 죽지 않았으면 OK로 간주
        return p.returncode >= 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False

# ---------- LLM 호출 ----------
def llm_generate_jsons(hints: Dict[str, Any], n=40, model="gpt-4o-mini",
                       temperature=1.1, api_key=None, base_url=None) -> List[str]:
    """
    OpenAI 호환 Responses API 호출 (python SDK v1.x).
    키/엔드포인트는 인수로 주입 (환경변수 의존 X).
    """
    prompt = f"""You are a fuzzing seed generator.

Generate {n} *diverse* JSON objects for robustness testing.
Requirements:
- One JSON object per line (JSON Lines). No code fences, no comments.
- Include boundary values (e.g., -1, 0, 1, 2^31-1, 2^31, 2^32-1), long/short strings, nulls, nested arrays/objects.
- Prefer keys if relevant: {hints.get('keys', [])[:64]}
- Add unusual structures: empty arrays/objects, deep nesting (depth 3~6), mixed types.
- Keep each object under ~4KB.
Output: only raw JSON objects, each on its own line.
"""

    # 1) 신형 SDK (권장)
    try:
        from openai import OpenAI
        kwargs = {}
        if api_key:  kwargs["api_key"]  = api_key
        if base_url: kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        resp = client.responses.create(
            model=model,
            input=prompt,
            temperature=float(temperature),
            max_output_tokens=min(8192, n * 256),
        )
        text = getattr(resp, "output_text", None)
        if not text:
            # 드문 호환 케이스
            text = "".join(getattr(c, "delta", "") for c in getattr(getattr(resp, "output", None), "choices", []) or [])
    except Exception as e1:
        # 2) 구버전 ChatCompletion 폴백
        try:
            import openai
            if api_key:  openai.api_key = api_key
            if base_url:
                # 구 SDK는 api_base
                openai.api_base = base_url
            chat = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=float(temperature),
            )
            text = chat["choices"][0]["message"]["content"]
        except Exception as e2:
            print(f"[rag] OpenAI call failed: {e1} / {e2}", file=sys.stderr)
            return []

    if not text:
        return []

    # 라인 단위 파싱 (코드펜스/빈줄/끝쉼표 제거)
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("```"):
            continue
        s = re.sub(r",\s*$", "", s)
        out.append(s)
    return out

# ---------- 메인 ----------
def main(bin_path: str, out_dir_seeds: str, out_dict: str, n=50, model="gpt-4o-mini",
         corpus_dirs: List[str]=None, out_dirs: List[str]=None, config_path: str|None=None):
    pathlib.Path(out_dir_seeds).mkdir(parents=True, exist_ok=True)
    pathlib.Path(os.path.dirname(out_dict)).mkdir(parents=True, exist_ok=True)

    llm_cfg = load_llm_config(config_path)
    # CLI가 모델을 주면 우선, 아니면 설정 파일의 모델 사용
    if not model: model = llm_cfg["model"]

    hints = gather_hints(corpus_dirs or ["corpus/json_seeds","corpus/generated"], out_dirs or [])
    cands = llm_generate_jsons(
        hints, n=n, model=model, temperature=llm_cfg["temperature"],
        api_key=llm_cfg["api_key"], base_url=llm_cfg["base_url"]
    )

    kept = 0
    for idx, line in enumerate(cands):
        if not parse_ok(line):
            continue
        if not fast_harness_ok(bin_path, line):
            continue
        ts = int(time.time())
        fn = os.path.join(out_dir_seeds, f"auto_{ts}_{idx:03d}.json")
        try:
            pathlib.Path(fn).write_text(line)
            kept += 1
            # 딕셔너리 후보: 최상위 키만 기록
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    with open(out_dict, "a") as f:
                        for k in obj.keys():
                            f.write(f"\"{k}\"\n")
            except Exception:
                pass
        except Exception:
            continue

    print(f"[rag] kept {kept}/{len(cands)}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True, help="Target harness binary (stdin accepts JSON)")
    ap.add_argument("--out-seeds", default="corpus/generated")
    ap.add_argument("--out-dict",  default="corpus/dict/auto.dict")
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--model", default=None, help="override model (else config.toml)")
    ap.add_argument("--corpus", nargs="*", default=["corpus/json_seeds","corpus/generated"])
    ap.add_argument("--outs", nargs="*", default=[], help="optional AFL out/ dirs to mine keys from")
    ap.add_argument("--config", default=None, help="path to TOML config (default: ~/.config/ragfuzz/config.toml)")
    args = ap.parse_args()
    main(args.bin, args.out_seeds, args.out_dict,
         n=args.n, model=args.model,
         corpus_dirs=args.corpus, out_dirs=args.outs,
         config_path=args.config)
