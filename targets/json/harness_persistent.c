#include <stdint.h>
#include <stdio.h>
#include <unistd.h>      // read()
#include <jansson.h>

/* AFL++가 제공하는 퍼즈 버퍼/길이 매크로 초기화 */
__AFL_FUZZ_INIT();

int main(void) {
  json_error_t err;

  /* 단일 퍼시스턴트 루프
     - AFL 실행 시: 공유메모리에서 케이스를 반복 제공
     - 비-AFL 실행(afl-showmap/직접 실행) 시: 최초 1회 stdin에서 읽어 자동 폴백
  */
  while (__AFL_LOOP(1000)) {
    const unsigned char* buf = __AFL_FUZZ_TESTCASE_BUF;
    size_t n = __AFL_FUZZ_TESTCASE_LEN;   // 비-AFL일 때는 read(0, ...)로 stdin 폴백

    json_t* root = json_loadb((const char*)buf, n, 0, &err);
    if (root) json_decref(root);
  }
  return 0;
}
