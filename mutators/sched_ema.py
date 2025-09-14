# mutators/sched_ema.py
import math, random

class EMAScheduler:
    def __init__(self, n_ops, lam=0.2, tau=0.8, eps=0.02):
        self.n_ops = int(n_ops)
        self.lam = float(lam)
        self.tau = float(tau)
        self.eps = float(eps)
        self.s = [0.0] * self.n_ops  # EMA 점수

    def reset_scores(self):
        self.s = [0.0] * self.n_ops

    def pick(self, allowed=None):
        # --- 방어: 허용 인덱스 정제 ---
        if allowed is None:
            allowed = list(range(self.n_ops))
        else:
            allowed = [int(i) for i in allowed if isinstance(i, int) and 0 <= int(i) < self.n_ops]
        if not allowed:
            # 안전 기본값: 0번 연산자(op_nop 등)
            allowed = [0]

        # 소프트맥스 샘플링(+ epsilon 탐색)
        logits = [self.tau * self.s[i] for i in allowed]
        m = max(logits)
        exps = [math.exp(x - m) for x in logits]
        Z = sum(exps) or 1.0
        probs = [e / Z for e in exps]

        # eps-explore
        k = len(allowed)
        probs = [(1.0 - self.eps) * p + (self.eps / k) for p in probs]

        r = random.random()
        acc = 0.0
        for idx, p in enumerate(probs):
            acc += p
            if r <= acc:
                return allowed[idx]
        return allowed[-1]

    def reward_update(self, op, d_cov=0.0, uniq_crash=False, new_path=False):
        # --- 방어: 범위 밖 인덱스 무시 ---
        if not isinstance(op, int) or not (0 <= op < self.n_ops):
            return
        # 간단한 보상 함수
        r = (0.7 * float(d_cov)) + (1.0 if uniq_crash else 0.0) + (0.2 if new_path else 0.0)
        self.s[op] = (1.0 - self.lam) * self.s[op] + self.lam * r