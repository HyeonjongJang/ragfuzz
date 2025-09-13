RAG-Guided Greybox Fuzzing (EoH-Only) — 사용 설명서

요약: 본 저장소는 LLM 없이도 동작하는 “RAG 아이디어 기반·자가적응(EoH-Only) 스케줄러” 그레이박스 퍼저의 MVP입니다.
핵심은 문법/딕셔너리/시드로 유효 입력 분포를 확장하고, 지수이동평균(EMA) 기반 스케줄러로 변이 연산자 비중을 경량 적응시키는 것입니다. 결과는 정적 리포트(HTML/PNG/CSV) 로 산출됩니다.

목차

요구 사항

디렉터리 구조

빠른 시작 (TL;DR)

설치 및 환경 구성

타깃 빌드

퍼징 실행

자가적응 스케줄러 & 보상 폴러

결과물(리포트) 생성

재현 체크리스트

문제 해결(Troubleshooting)

윤리·법적 안내

라이선스

요구 사항

운영체제: Ubuntu 22.04 (권장: Windows 10/11의 WSL2 Ubuntu 22.04)

WSL2 사용 시 **WSL 루트(예: ~/ragfuzz)**에서 작업하십시오. /mnt/c/... 경로는 I/O가 느려 성능 저하가 큽니다.

컴파일 도구: build-essential, clang/llvm, cmake, gdb/lldb

AFL++: afl-fuzz, afl-cc 등

라이브러리: libjansson-dev(JSON 파서용 예시 타깃)

Python 3.10+: matplotlib(그래프), 표준 라이브러리

QEMU/Unicorn 모드는 소스 없는 바이너리 퍼징에 필요합니다. 본 MVP는 소스 타깃(JSON 파서 하니스) 기준으로 동작하므로 필수는 아닙니다.

디렉터리 구조
ragfuzz/
├─ engine/
│  └─ reward_poller.py         # fuzzer_stats를 주기적으로 읽어 보상(EMA) 갱신 + 로그
├─ targets/
│  └─ json/
│     ├─ harness.c             # JSON 파서 하니스(예시)
│     └─ json_asan             # afl-cc로 빌드된 실행 파일(사용자 빌드 산출물)
├─ mutators/
│  ├─ __init__.py
│  └─ softmax_mutator.py       # EoH-Only 자가적응 스케줄러(AFL Python Custom Mutator)
├─ scripts/
│  ├─ metrics.py               # 커버리지/경로/크래시 그래프 + CSV 생성
│  └─ make_static_report.py    # 단일 HTML 리포트 생성
├─ triage/
│  └─ dedup.py                 # 간단 크래시 클러스터링(해시 기반)
├─ corpus/
│  ├─ seeds/                   # 초기 시드(.json)
│  ├─ dict/                    # 딕셔너리 토큰(.dict)
│  └─ grammar/                 # (선택) 문법/제약 정의
├─ reports/
│  └─ artifacts/               # PNG/CSV 산출물
└─ out/                        # AFL++ 실행 산출물(대용량; Git 추적 제외)

빠른 시작 (TL;DR)
# 0) 필수 패키지 및 AFL++ 설치
sudo apt update
sudo apt install -y build-essential clang llvm gdb lldb cmake git python3-pip \
                    libunwind-dev libjansson-dev afl++

# 1) (선택) Conda 환경
# conda create -n ragfuzz python=3.11 -y && conda activate ragfuzz
pip install matplotlib

# 2) 타깃 빌드(계측 + Sanitizers)
export CC=afl-cc
$CC -O2 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    targets/json/harness.c -o targets/json/json_asan -ljansson

# 3) 퍼징 시작 (기본)
mkdir -p out/json_asan
AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 AFL_NO_UI=1 \
afl-fuzz -i corpus/seeds -o out/json_asan -x corpus/dict/json.dict \
         -m none -t 100 -M f0 -- ./targets/json/json_asan

# 4) (선택) 자가적응 뮤테이터 + 보상 폴러
export PYTHONPATH="$(pwd):${PYTHONPATH}"
export AFL_PYTHON_MODULE=mutators.softmax_mutator
python3 engine/reward_poller.py  # 새 터미널에서 실행

# 5) 리포트 생성
python3 scripts/metrics.py
python3 triage/dedup.py
python3 scripts/make_static_report.py
# → reports/index.html 을 브라우저로 열기 (오프라인 가능)

설치 및 환경 구성
1) 시스템 패키지
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential clang llvm gdb lldb cmake git python3-pip \
                    libunwind-dev libjansson-dev afl++


afl-fuzz가 없다고 나오면: sudo apt install -y afl++ 로 해결됩니다.

2) (선택) Anaconda/Miniconda
# 설치 후
conda create -n ragfuzz python=3.11 -y
conda activate ragfuzz
pip install matplotlib

타깃 빌드

예시 타깃은 jansson JSON 파서를 이용한 간단 하니스입니다.

export CC=afl-cc
$CC -O2 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    targets/json/harness.c -o targets/json/json_asan -ljansson

# 빌드 검증(표준입력 수동 테스트)
echo '{"items":[1,2],"name":"x"}' | ./targets/json/json_asan ; echo $?

퍼징 실행
기본 실행
mkdir -p out/json_asan
AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 AFL_NO_UI=1 \
afl-fuzz -i corpus/seeds -o out/json_asan -x corpus/dict/json.dict \
         -m none -t 100 -M f0 -- ./targets/json/json_asan


-i: 시드 디렉터리

-o: 출력 루트(인스턴스는 f0/ 하위에 생성)

-x: 딕셔너리 파일

-t: 타임아웃(ms), 필요 시 50→100~200으로 조정

-M f0: 마스터 인스턴스 이름(여러 개 병렬 실행 가능)

실시간 UI를 보고 싶으면 AFL_NO_UI=1을 제거하고 실행하세요.

자가적응 스케줄러 & 보상 폴러
커스텀 뮤테이터(softmax) 활성화
export PYTHONPATH="$(pwd):${PYTHONPATH}"
export AFL_PYTHON_MODULE=mutators.softmax_mutator
# (선택) 디버그: export AFL_DEBUG=1

보상 폴러 실행(새 터미널)
python3 engine/reward_poller.py
# 예시 로그:
# [poller] tracking  out/json_asan/f0/fuzzer_stats
# [poller] inst=f0       cov= 40.00% (Δ40.00) paths=   123 (Δ  10) uniq=   1 NEW_CRASH


폴러는 out/**/fuzzer_stats를 자동 탐색하여 커버리지/경로/크래시 변화량을 EMA 보상에 반영합니다.

결과물(리포트) 생성

퍼저가 일정 시간 동작한 뒤 아래 스크립트로 정적 산출물을 만듭니다.

python3 scripts/metrics.py          # coverage/paths/crashes 그래프(PNG), metrics.csv
python3 triage/dedup.py             # 간단 크래시 클러스터(해시 기반) → triage.json
python3 scripts/make_static_report.py


생성물:

reports/artifacts/coverage.png, paths.png, crashes.png, metrics.csv

reports/triage.json

reports/index.html (단일 파일·오프라인 열람 가능)

이 파일들을 PPT에 그대로 삽입하시면 됩니다.

재현 체크리스트

afl-fuzz 설치 확인: which afl-fuzz

하니스 계측 빌드 확인: strings targets/json/json_asan | grep -i afl

시드/딕셔너리 존재: ls corpus/seeds, ls corpus/dict/json.dict

출력 경로: find out -name fuzzer_stats

큐 증가: ls out/json_asan/f0/queue | wc -l (증가해야 정상)

폴러 로그: python3 engine/reward_poller.py 실행 시 주기 로그 확인

문제 해결(Troubleshooting)

afl-fuzz: command not found
→ sudo apt install -y afl++

paths_total가 0에서 늘지 않음

하니스가 입력을 읽는지 확인:
cat corpus/seeds/seed_000.json | ./targets/json/json_asan ; echo $?

타임아웃 상향: -t 50 → -t 100~200

시드·딕셔너리 경로 점검

커스텀 뮤테이터가 로드되지 않음
→ export PYTHONPATH="$(pwd):$PYTHONPATH"
→ export AFL_PYTHON_MODULE=mutators.softmax_mutator (슬래시가 아닌 점 표기)

보상 폴러가 조용함
→ out/**/fuzzer_stats 경로가 없는 상태입니다. 퍼저가 먼저 돌아야 합니다.
→ 또는 out 하위가 아닌 다른 곳에 -o를 설정한 경우, 폴러가 못 찾을 수 있습니다.

WSL2 성능 저하
→ 작업 디렉터리를 ~/ragfuzz 등 Linux 파일시스템에 두고, /mnt/c/...는 피하세요.

윤리·법적 안내

본 프로젝트는 연구·교육 목적의 퍼징 도구입니다.

허가된 대상(오픈소스, 로컬 샌드박스) 에서만 사용하십시오.

외부 서비스/시스템에 무단으로 적용하는 행위는 법률·윤리에 어긋납니다.

크래시·PoC는 외부 유출 없이 책임 있게 취급하십시오.

라이선스

코드 라이선스: (예: MIT) — 필요에 따라 LICENSE 파일을 추가하세요.

포함 제3자 라이브러리의 라이선스는 각 프로젝트를 따릅니다.

문의

이슈·개선 제안은 GitHub Issues로 남겨 주세요.
재현 중 에러 로그/환경 정보를 함께 제공해 주시면 빠르게 도와드릴 수 있습니다.
