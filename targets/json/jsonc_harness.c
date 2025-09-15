#include <stdio.h>
#include <stdlib.h>
#include <json-c/json.h>

#ifndef __AFL_LOOP
#define __AFL_LOOP(x) for (int _i=0; _i<1; _i++)
#endif
#ifndef __AFL_INIT
#define __AFL_INIT() do {} while(0)
#endif

int main(void) {
  static unsigned char buf[1<<20]; // 1MB
  __AFL_INIT();
  while (__AFL_LOOP(1000)) {
    size_t n = fread(buf, 1, sizeof(buf)-1, stdin);
    if (!n) break;
    buf[n] = 0; // null-termination
    struct json_tokener *tok = json_tokener_new();
    json_object *obj = json_tokener_parse_ex(tok, (const char*)buf, (int)n);
    if (obj) json_object_put(obj);
    json_tokener_free(tok);
  }
  return 0;
}
