def afl_custom_init(*a, **k):
    open("/tmp/afl_pylog","a").write("INIT\n"); return 0
def afl_custom_fuzz(buf, add_buf, max_size, *a, **k):
    return bytes(buf[:max_size])
def afl_custom_deinit(*a, **k):
    open("/tmp/afl_pylog","a").write("DEINIT\n"); return 0
