#include <stdio.h>
#include <stdlib.h>
#include <yajl/yajl_tree.h>

#ifndef __AFL_LOOP
#define __AFL_LOOP(x) for (int _i=0; _i<1; _i++)
#endif
#ifndef __AFL_INIT
#define __AFL_INIT() do {} while(0)
#endif

int main(void){
  static unsigned char buf[1<<20];
  __AFL_INIT();
  while (__AFL_LOOP(1000)) {
    size_t n = fread(buf, 1, sizeof(buf)-1, stdin);
    if (!n) break;
    buf[n] = 0;
    char errbuf[1024];
    yajl_val root = yajl_tree_parse((const char*)buf, errbuf, sizeof(errbuf));
    if (root) yajl_tree_free(root);
  }
  return 0;
}
