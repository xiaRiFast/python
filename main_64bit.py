import time
import struct
from multiprocessing import shared_memory
import win32event
import pywintypes

# 配置参数 (必须与服务端完全一致)
SHM_NAME = "MySharedMemory"
REQUEST_EVENT_NAME = "RequestEvent"
RESPONSE_EVENT_NAME = "ResponseEvent"

# --- 连接到服务端创建的资源 ---
# 连接共享内存
shm = shared_memory.SharedMemory(name=SHM_NAME, create=False)
print(f"已连接到共享内存 '{SHM_NAME}'。")

# 连接到命名事件
try:
    hRequestEvent = win32event.OpenEvent(win32event.EVENT_ALL_ACCESS, False, REQUEST_EVENT_NAME)
    hResponseEvent = win32event.OpenEvent(win32event.EVENT_ALL_ACCESS, False, RESPONSE_EVENT_NAME)
    print("已连接到命名事件。")
except pywintypes.error as e:
    print(f"打开事件失败，请确保服务端已启动: {e}")
    exit()

# --- RPC 调用函数 ---
def call_add(a, b, timeout_ms=5000):
    # 1. 打包请求数据
    struct.pack_into('ii', shm.buf, 0, a, b)

    # 2. 触发请求事件，通知服务端
    win32event.SetEvent(hRequestEvent)

    # 3. 等待服务端的响应事件 (阻塞，直到被通知)
    ret = win32event.WaitForSingleObject(hResponseEvent, timeout_ms)
    if ret != win32event.WAIT_OBJECT_0:
        raise TimeoutError("等待响应超时")

    # 4. 从共享内存读取结果
    result = struct.unpack('i', shm.buf[8:12])[0]
    return result

# --- 性能测试 ---
if __name__ == "__main__":
    print("开始调用32位服务...")
    iterations = 1000

    start_time = time.perf_counter()
    for i in range(iterations):
        result = call_add(i, i+1)
        # if i % 100 == 0: print(f"Call {i}: {i} + {i+1} = {result}")
    end_time = time.perf_counter()

    total_time = (end_time - start_time) * 1000
    avg_time = total_time / iterations
    print(f"完成 {iterations} 次调用。")
    print(f"总耗时: {total_time:.2f} ms")
    print(f"平均延迟: {avg_time:.3f} ms")