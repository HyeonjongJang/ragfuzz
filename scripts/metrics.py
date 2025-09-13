import pathlib, matplotlib.pyplot as plt, csv, sys

def pick_base():
    outs = pathlib.Path("out")
    cands = sorted(outs.rglob("fuzzer_stats"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        print("[!] No fuzzer_stats under ./out", file=sys.stderr); sys.exit(1)
    base = cands[0].parent
    print(f"[i] Using: {base}")
    return base

base = pick_base()
stats_text = (base/"fuzzer_stats").read_text(errors="ignore").splitlines()
kv = {}
for line in stats_text:
    if ":" in line:
        k,v = line.split(":",1)
        kv[k.strip()] = v.strip()

U = int(kv.get("unique_crashes","0"))
P = int(kv.get("paths_total","0"))
Cstr = kv.get("bitmap_cvg","0%")
try: C = float(Cstr.split("%")[0])
except: C = 0.0

times, paths, crashes = [], [], []
pd = base/"plot_data"
if pd.exists():
    for line in pd.read_text().splitlines():
        if not line or line.startswith("#"): continue
        parts = line.split(",")
        try:
            ts = int(parts[0])
            pths = int(parts[3])       # paths_total
            crs  = int(parts[7])       # unique_crashes
        except (ValueError, IndexError):
            continue
        times.append(ts); paths.append(pths); crashes.append(crs)

art = pathlib.Path("reports/artifacts")
art.mkdir(parents=True, exist_ok=True)

# Coverage: 시간축이 없으므로 현재값을 수평선으로 표시
if times:
    import numpy as np
    xs = times
else:
    xs = list(range(2))

ys_cov = [C for _ in xs]
plt.figure(figsize=(7,4)); plt.plot(xs, ys_cov); plt.title(f"Coverage (bitmap_cvg ≈ {C:.1f}%)")
plt.xlabel("time (unix)"); plt.ylabel("%")
plt.savefig(art/"coverage.png", dpi=150); plt.close()

if times and paths:
    plt.figure(figsize=(7,4)); plt.plot(times, paths); plt.title("Paths (paths_total)")
    plt.xlabel("time (unix)"); plt.ylabel("count")
    plt.savefig(art/"paths.png", dpi=150); plt.close()

if times and crashes is not None:
    plt.figure(figsize=(7,4)); plt.plot(times, crashes); plt.title("Unique Crashes")
    plt.xlabel("time (unix)"); plt.ylabel("count")
    plt.savefig(art/"crashes.png", dpi=150); plt.close()

with open(art/"metrics.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["unique_crashes","paths_total","bitmap_cvg_pct"])
    w.writerow([U,P,C])
print("[i] Wrote reports/artifacts/{coverage,paths,crashes}.png and metrics.csv")
