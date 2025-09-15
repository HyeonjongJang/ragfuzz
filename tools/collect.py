#!/usr/bin/env python3
import argparse, csv, os, glob

def read_fuzzer_stats(path):
    d = {}
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if ":" in line:
                k, v = line.strip().split(":", 1)
                d[k.strip()] = v.strip()
    return d

def last_plot_row(path):
    if not os.path.exists(path): return None, None
    last = None
    header = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("#"):
                header = line.strip("# \n")
                continue
            if line.strip():
                last = line.strip().split(",")
    return header, last

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("csv_out")
    args = ap.parse_args()

    rows = []
    for stats_path in glob.glob(os.path.join(args.outdir, "**", "fuzzer_stats"), recursive=True):
        fuzzer_dir = os.path.dirname(stats_path)
        pd_path = os.path.join(fuzzer_dir, "plot_data")
        st = read_fuzzer_stats(stats_path)
        hdr, last = last_plot_row(pd_path)

        row = {
            "fuzzer_dir": fuzzer_dir,
            "paths_total": st.get("paths_total", ""),
            "edges_found": st.get("edges_found", ""),
            "execs_done": st.get("execs_done", ""),
            "execs_per_sec": st.get("execs_per_sec", ""),
            "unique_crashes": st.get("unique_crashes", ""),
            "unique_hangs": st.get("unique_hangs", ""),
        }
        if last:
            # AFL++ plot_data는 보통 마지막 컬럼이 edges_found
            row["plot_unix_time"] = last[0] if len(last) > 0 else ""
            row["plot_cycles_done"] = last[1] if len(last) > 1 else ""
            row["plot_cur_path"] = last[2] if len(last) > 2 else ""
            row["plot_paths_total"] = last[3] if len(last) > 3 else ""
            row["plot_execs_per_sec"] = last[10] if len(last) > 10 else ""
            row["plot_total_execs"] = last[11] if len(last) > 11 else ""
            row["plot_edges_found"] = last[-1]
        rows.append(row)

    cols = sorted({k for r in rows for k in r.keys()})
    with open(args.csv_out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows: w.writerow(r)

if __name__ == "__main__":
    main()
