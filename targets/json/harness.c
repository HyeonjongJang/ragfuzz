#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
#include <jansson.h>

int main(void) {
    static unsigned char buf[1 << 20];  // 1MB
    size_t n = fread(buf, 1, sizeof(buf), stdin);
    if (n == 0) {
        return 0;
    }

    json_error_t error;
    json_t *root = json_loadb((const char *)buf, n, 0, &error);
    if (root) {
        json_decref(root);
    } else {
        // 파싱 실패시에도 0 반환: 경로 다양성 확보 목적
        // fprintf(stderr, "parse error at line %d: %s\n", error.line, error.text);
    }
    return 0;
}
