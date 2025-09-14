def afl_custom_init(seed):
    return 0

def afl_custom_deinit():
    return 0

def afl_custom_post_process(buf):
    try:
        return bytes(buf or b"")
    except Exception:
        return b""

def afl_custom_fuzz(buf, add_buf, max_size):
    if not buf:
        buf = b"\n"
    if not max_size or max_size <= 0:
        max_size = max(1, len(buf))
    return bytes(buf[:max_size])
