def init(seed): 
    return 0

def fuzz(buf, add_buf, max_size):
    # 항상 1바이트만 반환 (안전하게 경로만 검증)
    return b'X'

def deinit():
    pass
