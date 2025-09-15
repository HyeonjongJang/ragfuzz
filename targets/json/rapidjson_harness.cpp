#include <cstdio>
#include "rapidjson/document.h"
using namespace rapidjson;

#ifndef __AFL_LOOP
#define __AFL_LOOP(x) for (int _i=0; _i<1; _i++)
#endif
#ifndef __AFL_INIT
#define __AFL_INIT() do {} while(0)
#endif

int main(){
  static char buf[1<<20];
  __AFL_INIT();
  while (__AFL_LOOP(1000)) {
    size_t n = fread(buf, 1, sizeof(buf)-1, stdin);
    if (!n) break;
    buf[n] = '\0';              // ParseInsitu 요구
    Document d;
    d.ParseInsitu(buf);         // in-situ 파싱
  }
  return 0;
}