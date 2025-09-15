#!/usr/bin/env python3
import os, sys, subprocess, hashlib, glob

target = sys.argv[1]
crash_dir = sys.argv[2]
env = os.environ.copy()
env["ASAN_OPTIONS"] = "abort_on_error=1:symbolize=0:handle_segv=1"

clusters = {}
for path in glob.glob(os.path.join(crash_dir, "id:*")):
    try:
        p = subprocess.run([target], input=open(path,"rb").read(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env, timeout=2)
    except Exception as e:
        out = str(e).encode()
    else:
        out = p.stderr or b""
    sig = b"\n".join([ln for ln in out.splitlines() if b" at " in ln or b"#" in ln])[:4096]
    h = hashlib.sha1(sig).hexdigest()[:12]
    clusters.setdefault(h, []).append(os.path.basename(path))

for h, items in sorted(clusters.items(), key=lambda x: -len(x[1])):
    print(f"[{h}] x{len(items)}")
    for it in items[:5]: print("  ", it)
