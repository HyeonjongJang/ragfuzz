import sys, os, glob, csv
from pathlib import Path

def parse_stats(fp):
    out = {}
    with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if ':' in line:
                k,v = line.split(':',1)
                out[k.strip()] = v.strip()
    return out

def human(name):
    # 예: out/3way_YYMMDD_HHMMSS/base_default/default -> base_default
    p = Path(name)
    try:
        return p.parent.name  # default 상위 폴더 이름
    except Exception:
        return str(p)

def main(root):
    rows = []
    for inst in sorted(glob.glob(os.path.join(root, "*", "default", "fuzzer_stats"))):
        s = parse_stats(inst)
        rows.append({
            "run": human(inst),
            "bitmap_cvg": s.get("bitmap_cvg",""),
            "paths_total": int(s.get("paths_total","0")),
            "execs_done": int(s.get("execs_done","0")),
            "execs_per_sec": float(s.get("execs_per_sec","0")),
            "unique_crashes": int(s.get("unique_crashes","0")),
            "unique_hangs": int(s.get("unique_hangs","0")),
        })

    if not rows:
        print("No fuzzer_stats found under", root)
        sys.exit(1)

    # 정렬: paths_total, execs_per_sec 기준
    rows.sort(key=lambda r: (-r["paths_total"], -r["execs_per_sec"]))

    # 콘솔 표
    hdr = ["run","paths_total","bitmap_cvg","execs_done","execs_per_sec","unique_crashes","unique_hangs"]
    widths = [max(len(str(r[h])) for r in rows + [{h:h}]) for h in hdr]
    line = " | ".join(h.ljust(w) for h,w in zip(hdr,widths))
    print(line)
    print("-" * len(line))
    for r in rows:
        print(" | ".join(str(r[h]).ljust(w) for h,w in zip(hdr,widths)))

    # CSV 저장
    csv_path = os.path.join(root, "comparison.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("\n[+] wrote:", csv_path)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python compare_afl_stats.py <OUT_ROOT>")
        sys.exit(2)
    main(sys.argv[1])
