# engine/reward_poller.py
# AFL++ fuzzer_stats를 주기적으로 읽어 mutator 보상(EMA) 갱신 + 콘솔 로그 출력
import os, time, glob, re, collections
import mutators.softmax_mutator as M

BASE = "out"  # out/ 이하 어디에 있든 자동 탐색

def _to_float(s, default=0.0):
    try: return float(str(s).strip().rstrip("%"))
    except Exception:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(s) or "")
        return float(m.group(1)) if m else default

def _to_int(s, default=0):
    try: return int(str(s).strip())
    except Exception:
        try: return int(float(str(s).strip().rstrip("%")))
        except Exception:
            m = re.search(r"([0-9]+)", str(s) or ""); return int(m.group(1)) if m else default

def _read_stats(path):
    d={}
    try:
        with open(path,"r") as f:
            for line in f:
                if ":" in line:
                    k,v=line.split(":",1)
                    d[k.strip()]=v.strip()
    except FileNotFoundError:
        return None
    return d

def _discover_stats():
    # out/*/fuzzer_stats 와 out/*/*/fuzzer_stats 모두 탐색
    paths = glob.glob(os.path.join(BASE, "*", "fuzzer_stats")) + \
            glob.glob(os.path.join(BASE, "*", "*", "fuzzer_stats"))
    # 최신 수정순으로 정렬
    paths = sorted(paths, key=lambda p: os.path.getmtime(p), reverse=True)
    return paths

if __name__=="__main__":
    prev = collections.defaultdict(lambda: {"cov":0.0,"paths":0,"uniq":0})
    seen_paths = set()

    while True:
        paths = _discover_stats()
        if not paths:
            print("[poller] No fuzzer_stats under ./out yet. Is afl-fuzz running?")
            time.sleep(5)
            continue

        for sp in paths:
            inst = os.path.basename(os.path.dirname(sp))  # e.g., f0, default
            s = _read_stats(sp)
            if not s: continue

            cov   = _to_float(s.get("bitmap_cvg","0"))      # e.g., "40.00%"
            uniq  = _to_int(s.get("unique_crashes","0"))
            paths_total = _to_int(s.get("paths_total","0"))

            pc = prev[sp]
            d_cov   = max(0.0, cov - pc["cov"])
            d_paths = max(0,   paths_total - pc["paths"])
            new_cr  = uniq > pc["uniq"]

            # 보상 갱신(간단히 전체 연산자에 동일 분배)
            M.update_reward(d_cov, new_cr, d_paths)

            # 첫 발견 경로는 공지
            if sp not in seen_paths:
                print(f"[poller] tracking  {sp}")
                seen_paths.add(sp)

            print(f"[poller] inst={inst:8s} cov={cov:6.2f}% (Δ{d_cov:4.2f}) "
                  f"paths={paths_total:7d} (Δ{d_paths:4d}) uniq={uniq:4d} "
                  f"{'NEW_CRASH' if new_cr else ''}")

            prev[sp] = {"cov":cov,"paths":paths_total,"uniq":uniq}

        time.sleep(30)
