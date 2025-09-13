import os, json, hashlib, sys, pathlib
def pick_base():
    cands = sorted(pathlib.Path("out").rglob("fuzzer_stats"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        print("[!] No fuzzer_stats under ./out", file=sys.stderr); sys.exit(1)
    return cands[0].parent

base = pick_base()
crashes = base/"crashes"
groups = {}
if crashes.is_dir():
    for f in os.listdir(crashes):
        if f.startswith("id:") and ",sig" in f:
            p = crashes/ f
            h = hashlib.md5(open(p,"rb").read(4096)).hexdigest()
            groups.setdefault(h, []).append(str(p))

report = [{"hash":h,"count":len(v),"samples":v[:3]} for h,v in groups.items()]
pathlib.Path("reports").mkdir(exist_ok=True)
json.dump(report, open("reports/triage.json","w"), indent=2)
print(f"[i] Wrote reports/triage.json with {len(report)} clusters")
