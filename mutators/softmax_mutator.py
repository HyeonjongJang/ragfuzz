# AFL++ Python Custom Mutator with shared JSON state (new/old API compatible)
import os, random, math, struct, json

# --- config/state ---
OPS = ["bitflip","arith","havoc","splice","dict_ins","len_skew","grammar_ins"]
STATE_PATH = os.environ.get("RAGFUZZ_STATE", "mutators/state.json")

ema    = {op: 0.0 for op in OPS}
counts = {op: 1   for op in OPS}
_lambda = 0.2
_tau     = 3.0
_epsilon = 0.03

_last_load = 0.0
def _maybe_load_state():
  """Reload EMA/counts from STATE_PATH if modified by reward_poller."""
  global ema, counts, _last_load
  try:
    st = os.stat(STATE_PATH)
    if st.st_mtime <= _last_load:
      return
    with open(STATE_PATH, "r") as f:
      data = json.load(f)
    if "ema" in data:
      for k in OPS:
        if k in data["ema"]:
          ema[k] = float(data["ema"][k])
    if "counts" in data:
      for k in OPS:
        if k in data["counts"]:
          counts[k] = int(data["counts"][k])
    _last_load = st.st_mtime
  except Exception:
    # state 파일이 없거나 파싱 실패 시 조용히 무시
    pass

def _softmax(scores):
  m = max(scores)
  exps = [math.exp((s - m) * _tau) for s in scores]
  s = sum(exps)
  return [e / s for e in exps] if s > 0 else [1.0/len(scores)]*len(scores)

def _choose_op():
  _maybe_load_state()
  if random.random() < _epsilon:
    return random.choice(OPS)
  scores = [ema[o] + math.sqrt(1.0 / max(1, counts[o])) for o in OPS]
  probs  = _softmax(scores)
  return random.choices(OPS, weights=probs, k=1)[0]

def _mutate_bytes(data: bytearray, op: str) -> bytearray:
  b = bytearray(data)
  if op == "bitflip" and len(b) > 0:
    i = random.randrange(len(b)); b[i] ^= 1 << random.randrange(8)
  elif op == "arith" and len(b) > 1:
    i = random.randrange(len(b)-1)
    val = struct.unpack_from("<H", b, i)[0]
    struct.pack_into("<H", b, i, (val + random.choice([-1,1,255])) & 0xFFFF)
  elif op == "havoc" and len(b) > 0:
    for _ in range(random.randint(1,4)):
      j = random.randrange(len(b)); b[j] = random.randrange(256)
  elif op == "splice":
    try:
      cand=[p for p in os.listdir("queue") if p.startswith("id:")]
      if cand:
        with open(os.path.join("queue", random.choice(cand)),"rb") as f:
          other=bytearray(f.read())
        cut=min(len(b), len(other), random.randint(1,16))
        b[:cut]=other[:cut]
    except Exception:
      pass
  elif op == "dict_ins":
    try:
      toks=[]
      with open("corpus/dict/json.dict","r",encoding="utf-8") as f:
        for t in f:
          t=t.strip()
          if t: toks.append(t.strip('"'))
      if toks:
        t=random.choice(toks).encode("utf-8","ignore")
        pos=random.randrange(len(b)+1); b[pos:pos]=t
    except Exception:
      pass
  elif op == "len_skew" and len(b)>0:
    if random.random()<0.5 and len(b)>4:
      del b[random.randrange(len(b)-1)]
    else:
      b.insert(random.randrange(len(b)+1), random.randrange(256))
  elif op == "grammar_ins":
    toks=[b'0', b'""', b'[]', b'{}', b'\n']
    t=random.choice(toks); pos=random.randrange(len(b)+1); b[pos:pos]=t
  return b

# --- AFL++ Python Mutator API ---
# 구표기(afl_custom_*)와 신표기(init/deinit/fuzz/...) 모두 제공

# old-style
def afl_custom_init(_):  # seed param is ignored
  return 0

def afl_custom_deinit():
  return 0

def afl_custom_fuzz(buf, add_buf, max_size):
    try:
        op = _choose_op()
        out = _mutate_bytes(bytearray(buf), op)
        if not isinstance(out, (bytes, bytearray)):
            return bytes(buf[:max_size])
        return bytes(out[:max_size])
    except Exception:
        return bytes(buf[:max_size])

def afl_custom_post_process(buf):
    # 반드시 bytes를 반환
    try:
        return bytes(buf)
    except Exception:
        return b""

def afl_custom_queue_new_entry(filename, orig_filename):
  # no-op hook
  return 0

# (optional trimming hooks as no-ops)
def afl_custom_init_trim(buf): return 0
def afl_custom_trim(max_size): return None
def afl_custom_post_trim(success): return 0

# new-style
def init(seed=None):
  return afl_custom_init(seed)

def deinit():
  return afl_custom_deinit()

def fuzz(buf, add_buf, max_size):
    # AFL++의 신규 표기. 방어 로직은 afl_custom_fuzz 쪽에 이미 있음.
    return afl_custom_fuzz(buf, add_buf, max_size)

def post_process(buf):
  return afl_custom_post_process(buf)

def queue_new_entry(filename, orig_filename):
  return afl_custom_queue_new_entry(filename, orig_filename)