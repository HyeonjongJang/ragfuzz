# write EMA state to mutators/state.json so AFL-side mutator can read it
import os, time, glob, re, json, collections

BASE = "out"
STATE_PATH = os.environ.get("RAGFUZZ_STATE","mutators/state.json")

def _to_float(s, default=0.0):
  try: return float(str(s).strip().rstrip("%"))
  except Exception:
    m=re.search(r"([0-9]+(?:\.[0-9]+)?)", str(s) or ""); return float(m.group(1)) if m else default

def _to_int(s, default=0):
  try: return int(str(s).strip())
  except Exception:
    try: return int(float(str(s).strip().rstrip("%")))
    except Exception:
      m=re.search(r"([0-9]+)", str(s) or ""); return int(m.group(1)) if m else default

def _read_stats(path):
  d={}
  try:
    with open(path,"r") as f:
      for line in f:
        if ":" in line:
          k,v=line.split(":",1); d[k.strip()]=v.strip()
  except FileNotFoundError:
    return None
  return d

def _discover_stats():
  paths = glob.glob(os.path.join(BASE,"*","fuzzer_stats")) + \
          glob.glob(os.path.join(BASE,"*","*","fuzzer_stats"))
  paths = sorted(paths, key=lambda p: os.path.getmtime(p), reverse=True)
  return paths

# 공유 상태
OPS=["bitflip","arith","havoc","splice","dict_ins","len_skew","grammar_ins"]
ema={op:0.0 for op in OPS}
counts={op:1 for op in OPS}
_lambda=0.2

def _save_state():
  os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
  tmp=STATE_PATH+".tmp"
  with open(tmp,"w") as f:
    json.dump({"ema":ema,"counts":counts}, f)
  os.replace(tmp, STATE_PATH)

if __name__=="__main__":
  prev = collections.defaultdict(lambda: {"cov":0.0,"paths":0,"uniq":0})
  seen=set()
  while True:
    paths=_discover_stats()
    if not paths:
      print("[poller] waiting afl-fuzz ...")
      time.sleep(5); continue
    for sp in paths:
      s=_read_stats(sp)
      if not s: continue
      cov=_to_float(s.get("bitmap_cvg","0"))
      uniq=_to_int(s.get("unique_crashes","0"))
      total=_to_int(s.get("paths_total","0"))
      pc=prev[sp]
      d_cov=max(0.0, cov-pc["cov"])
      d_paths=max(0, total-pc["paths"])
      new_cr= uniq>pc["uniq"]

      # 동일 보상 분배(안정적)
      r = 1.0*d_cov + 5.0*(1 if new_cr else 0) + 0.3*d_paths
      for o in OPS:
        ema[o]=(1-_lambda)*ema[o]+_lambda*r
        counts[o]+=1

      if sp not in seen:
        print(f"[poller] tracking {sp}"); seen.add(sp)
      print(f"[poller] cov={cov:6.2f}% (Δ{d_cov:4.2f}) paths={total:7d} (Δ{d_paths:4d}) uniq={uniq:4d} {'NEW_CRASH' if new_cr else ''}")

      prev[sp]={"cov":cov,"paths":total,"uniq":uniq}
    _save_state()
    time.sleep(30)
