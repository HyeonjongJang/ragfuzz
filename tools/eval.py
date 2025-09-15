#!/usr/bin/env python3
"""
AFL++ 결과 집계 스크립트 (coverage/TTFC/execs/sec 요약 & 그래프)
- 입력: --out <afl_out_dir>  (예: out/exp_20250101_000000/afl)
- 출력: --save summary.csv, --png summary.png
- 차트는 matplotlib만 사용(색상/스타일 지정 없음).
"""
import argparse
import csv
import os
import glob
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

def parse_fuzzer_stats(p: Path) -> Dict[str, str]:
    d = {}
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if ":" in line:
                k, v = line.strip().split(":", 1)
                d[k.strip()] = v.strip()
    return d

def read_plot_data(p: Path) -> List[Tuple[float, int, int, int, int, int, int, int, int, float]]:
    """
    Returns list of tuples:
    (unix_time, cycles_done, paths_total, pending_total, pending_favs,
     map_size, unique_crashes, unique_hangs, max_depth, execs_per_sec)
    """
    out = []
    if not p.exists():
        return out
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split(",")
            if len(parts) < 10:
                # older/newer formats may differ; try best-effort
                parts += ["0"] * (10 - len(parts))
            try:
                row = (
                    float(parts[0]),
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                    int(parts[4]),
                    int(parts[5]),
                    int(parts[6]),
                    int(parts[7]),
                    int(parts[8]),
                    float(parts[9]),
                )
                out.append(row)
            except Exception:
                continue
    return out

def first_ttfc_seconds(plot: List[Tuple]) -> Optional[float]:
    if not plot:
        return None
    t0 = plot[0][0]
    prev_cr = 0
    for (ts, *_rest) in plot:
        unique_cr = _rest[5]  # index 6 overall; after ts + 5 fields
        if unique_cr > 0 and prev_cr == 0:
            return ts - t0
        prev_cr = unique_cr
    return None

def scan_instances(out_dir: Path) -> List[Path]:
    # 기대 구조: out_dir/<id>/{fuzzer_stats,plot_data,queue,crashes}
    # (마스터 m, 슬레이브 s1,s2,... 또는 default/nvd1 등)
    return [p for p in out_dir.iterdir() if p.is_dir()]

def summarize(out_dir: Path) -> List[Dict[str, object]]:
    rows = []
    for inst in scan_instances(out_dir):
        stats = inst / "fuzzer_stats"
        plot = inst / "plot_data"
        if not stats.exists():
            continue
        st = parse_fuzzer_stats(stats)
        plot_rows = read_plot_data(plot)
        ttfc = first_ttfc_seconds(plot_rows)

        # 마지막 포인트로 커버리지·속도 추출(없으면 0)
        map_density = float(st.get("map_density", st.get("bitmap_cvg", "0")).split("%")[0]) if st.get("map_density") or st.get("bitmap_cvg") else 0.0
        execs_done = int(st.get("execs_done", "0"))
        execs_per_sec = float(st.get("execs_per_sec", "0"))
        paths_total = int(st.get("paths_total", "0"))
        unique_crashes = int(st.get("unique_crashes", "0"))

        rows.append({
            "instance": inst.name,
            "paths_total": paths_total,
            "map_density_percent": map_density,
            "execs_done": execs_done,
            "execs_per_sec": execs_per_sec,
            "unique_crashes": unique_crashes,
            "ttfc_sec": ttfc if ttfc is not None else -1,
        })
    return rows

def save_csv(rows: List[Dict[str, object]], path: Path) -> None:
    if not rows:
        return
    keys = ["instance","paths_total","map_density_percent","execs_done","execs_per_sec","unique_crashes","ttfc_sec"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def draw_png(rows: List[Dict[str, object]], out_path: Path) -> None:
    if not rows:
        return
    # 간단 비교: paths_total, map_density, unique_crashes
    rows = sorted(rows, key=lambda r: r["instance"])
    x = [r["instance"] for r in rows]
    y_paths = [r["paths_total"] for r in rows]
    y_cov = [r["map_density_percent"] for r in rows]
    y_cr = [r["unique_crashes"] for r in rows]

    plt.figure(figsize=(10, 6))
    plt.subplot(3,1,1)
    plt.bar(x, y_paths)
    plt.ylabel("paths_total")
    plt.xticks(rotation=45, ha="right")

    plt.subplot(3,1,2)
    plt.bar(x, y_cov)
    plt.ylabel("map_density(%)")
    plt.xticks(rotation=45, ha="right")

    plt.subplot(3,1,3)
    plt.bar(x, y_cr)
    plt.ylabel("unique_crashes")
    plt.xticks(rotation=45, ha="right")

    plt.tight_layout()
    plt.savefig(out_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="afl output root (e.g., out/exp_xxx/afl)")
    ap.add_argument("--save", default=None, help="summary csv path")
    ap.add_argument("--png", default=None, help="summary png path")
    args = ap.parse_args()

    out_dir = Path(args.out)
    rows = summarize(out_dir)

    if args.save:
        save_csv(rows, Path(args.save))
        print(f"[i] saved CSV: {args.save}")
    if args.png:
        draw_png(rows, Path(args.png))
        print(f"[i] saved PNG: {args.png}")

    # 콘솔 요약
    if rows:
        print("\ninstance\tpaths\tcov(%)\texecs/s\tuniq_cr\tTTFC(s)")
        for r in rows:
            print(f"{r['instance']}\t{r['paths_total']}\t{r['map_density_percent']:.2f}\t{r['execs_per_sec']:.1f}\t{r['unique_crashes']}\t{int(r['ttfc_sec']) if r['ttfc_sec']!=-1 else -1}")

if __name__ == "__main__":
    main()
