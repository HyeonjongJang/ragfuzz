def init(seed):
    return 0

def fuzz(buf, add_buf, max_size):
    # AFL++가 넘겨주는 memoryview/bytearray/bytes 를 모두 bytes 로 보정
    if isinstance(buf, memoryview):
        data = buf.tobytes()
    elif isinstance(buf, bytearray):
        data = bytes(buf)
    elif isinstance(buf, bytes):
        data = buf
    else:
        data = bytes(buf)

    # 길이 보정
    if len(data) > max_size:
        data = data[:max_size]
    if not data:
        data = b'X'  # 빈 버퍼 방지

    return data

def deinit():
    pass
