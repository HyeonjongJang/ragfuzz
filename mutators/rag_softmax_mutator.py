# AFL++ Python custom mutator (numpy 無 / 시그니처 유연)
import os, random, math, struct

OPS = ["bitflip","arith","havoc","splice","dict_ins","len_skew","grammar_ins"]
ema   = {op: 0.0 for op in OPS}
counts= {op: 1   for op in OPS}
lambda_ = 0.2
tau     = 3.0
epsilon = 0.03

def _softmax(scores):
    m = max(scores)
    exps = [math.exp((s - m) * tau) for s in scores]
    s = sum(exps)
    return [e/s for e in exps] if s > 0 else [1.0/len(scores)]*len(scores)

def _choose_op():
    if random.random() < epsilon:
        return random.choice(OPS)
    scores=[ema[o] + math.sqrt(1.0/max(1,counts[o])) for o in OPS]
    probs=_softmax(scores)
    return random.choices(OPS, weights=probs, k=1)[0]

def _mutate_bytes(data: bytearray, op: str) -> bytearray:
    b = bytearray(data)
    if op=="bitflip" and len(b)>0:
        i=random.randrange(len(b)); b[i]^=1<<random.randrange(8)
    elif op=="arith" and len(b)>1:
        i=random.randrange(len(b)-1); val=struct.unpack_from("<H", b, i)[0]
        struct.pack_into("<H", b, i, (val + random.choice([-1,1,255])) & 0xFFFF)
    elif op=="havoc":
        for _ in range(random.randint(1,4)):
            if len(b)==0: break
            j=random.randrange(len(b)); b[j]=random.randrange(256)
    elif op=="splice":
        try:
            qs=[p for p in os.listdir("queue") if p.startswith("id:")]
            if qs:
                with open(os.path.join("queue", random.choice(qs)),"rb") as f:
                    other=bytearray(f.read())
                cut=min(len(b), len(other), random.randint(1,16))
                b[:cut]=other[:cut]
        except: pass
    elif op=="dict_ins":
        try:
            toks=[]
            with open("corpus/dict/json.dict","r",encoding="utf-8") as f:
                for t in f:
                    t=t.strip()
                    if t: toks.append(t.strip('"'))
            if toks:
                t=random.choice(toks).encode("utf-8","ignore")
                pos=random.randrange(len(b)+1); b[pos:pos]=t
        except: pass
    elif op=="len_skew" and len(b)>0:
        if random.random()<0.5 and len(b)>4: del b[random.randrange(len(b)-1)]
        else: b.insert(random.randrange(len(b)+1), random.randrange(256))
    elif op=="grammar_ins":
        toks=[b'0', b'""', b'[]', b'{}', b'\n']
        t=random.choice(toks); pos=random.randrange(len(b)+1); b[pos:pos]=t
    return b

# ---- AFL++ Python API (유연 시그니처) ----
def afl_custom_init(*args, **kwargs):
    try:
        with open("/tmp/afl_pylog","a") as f: f.write("init called\n")
    except Exception: pass
    return 0

def afl_custom_deinit(*args, **kwargs):
    try:
        with open("/tmp/afl_pylog","a") as f: f.write("deinit called\n")
    except Exception: pass
    return 0

def afl_custom_fuzz(buf, add_buf, max_size, *args, **kwargs):
    # 최소 요구 시그니처: (buf, add_buf, max_size)
    op = _choose_op()
    out = _mutate_bytes(bytearray(buf), op)
    return bytes(out[:max_size])

# 외부 보상 업데이트(폴러가 주기적으로 호출)
def update_reward(delta_cov, new_crash, novel_path):
    r = 1.0*delta_cov + 5.0*(1 if new_crash else 0) + 0.3*novel_path
    for o in OPS:
        ema[o] = (1-lambda_)*ema[o] + lambda_*r
        counts[o]+=1
