import time, json, pathlib, argparse

def read_stats(fp):
    d = {}
    with open(fp, "r") as f:
        for line in f:
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
    return d

def main(out_dir, window_sec=180, k=3, interval=5):
    out = pathlib.Path(out_dir)
    fuzzer_stats = out / "default" / "fuzzer_stats"
    ctl_file     = out / "default" / "phase_ctl.json"
    hist = []
    print(f"[phase-ctl] watching {fuzzer_stats}")
    while True:
        try:
            s = read_stats(fuzzer_stats)
            now = time.time()
            paths_total = int(s.get("paths_total", "0"))
            hist.append((now, paths_total))
            # 최근 window_sec 구간만 유지
            hist = [(t, p) for (t, p) in hist if now - t <= window_sec]
            plateau = False
            if len(hist) >= 2:
                delta = hist[-1][1] - hist[0][1]
                plateau = (delta < k)
            ctl_file.write_text(json.dumps({"plateau": plateau}))
        except FileNotFoundError:
            # 아직 fuzzer_stats가 안 생겼을 때
            pass
        except Exception:
            # 조용히 재시도
            pass
        time.sleep(interval)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=int, default=180)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--interval", type=int, default=5)
    args = ap.parse_args()
    main(args.out, args.window, args.k, args.interval)
