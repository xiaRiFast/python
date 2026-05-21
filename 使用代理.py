import requests

def get_proxy():
    """从代理池获取一个代理"""
    response = requests.get("http://127.0.0.1:5010/get/")
    return response.json().get("proxy")

def delete_proxy(proxy):
    """从代理池中删除无效代理"""
    requests.get(f"http://127.0.0.1:5010/delete/?proxy={proxy}")

# 示例：使用代理访问
proxy = get_proxy()
print(f"获取到代理: {proxy}")

# 尝试用代理访问一个网站来测试它
proxies = {
    "http": f"http://{proxy}",
    "https": f"https://{proxy}",
}
try:
    test_response = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=10)
    print(f"代理可用，你的出口IP: {test_response.text}")
except:
    print("代理不可用，删除它")
    delete_proxy(proxy)
