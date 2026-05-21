"""
异步代理池 —— 抓取免费代理并验证可用性
"""

import asyncio
import aiohttp
import random
import re
import urllib.request
from collections import deque


class ProxyPool:
    """简单的异步代理池，不依赖第三方库"""

    def __init__(self, max_proxies=50, max_concurrent_checks=100):
        self.pool = deque()
        self.max_proxies = max_proxies
        self._session = None
        self._semaphore = asyncio.Semaphore(max_concurrent_checks)

    async def _get_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    # ==================== 代理抓取 ====================

    async def _fetch_proxies(self):
        """从多个免费代理源抓取，逐个尝试"""
        proxies = []
        fetchers = [
            self._fetch_89ip,
            self._fetch_kuaidaili,
            self._fetch_kuaidaili_page2,
            self._fetch_xiaohuan,
            self._fetch_ip3366,
            self._fetch_ip3366_page2,
        ]
        for fetcher in fetchers:
            if len(proxies) >= self.max_proxies * 3:
                break
            try:
                result = await fetcher()
                if result:
                    print(f"[抓取] 获取 {len(result)} 个候选")
                    proxies.extend(result)
            except Exception:
                pass

        proxies = list(dict.fromkeys(proxies))
        random.shuffle(proxies)
        return proxies[:self.max_proxies * 3]

    async def _fetch_89ip(self):
        """89免费代理（国内，纯文本）"""
        proxies = []
        try:
            req = urllib.request.Request(
                "https://www.89ip.cn/tqdl.html?api=1&num=100&port=&address=&isp=",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=15, context=None) as resp:
                text = resp.read().decode("gbk", errors="ignore")
                for line in text.strip().splitlines():
                    line = line.strip()
                    m = re.match(r'^(\d{1,3}(?:\.\d{1,3}){3})[:\s\t]+(\d{2,5})', line)
                    if m:
                        proxies.append(f"http://{m.group(1)}:{m.group(2)}")
        except Exception:
            pass
        return proxies

    async def _fetch_kuaidaili(self):
        """快代理第1页（国内高匿）"""
        return await self._fetch_kuaidaili_page("https://www.kuaidaili.com/free/inha/1/")

    async def _fetch_kuaidaili_page2(self):
        """快代理第2页"""
        return await self._fetch_kuaidaili_page("https://www.kuaidaili.com/free/inha/2/")

    async def _fetch_kuaidaili_page(self, url):
        """快代理通用解析"""
        proxies = []
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                matches = re.findall(
                    r'<td[^>]*>\s*(\d{1,3}(?:\.\d{1,3}){3})\s*</td>\s*<td[^>]*>\s*(\d{2,5})\s*</td>',
                    text
                )
                for host, port in matches:
                    proxies.append(f"http://{host}:{port}")
        except Exception:
            pass
        return proxies

    async def _fetch_xiaohuan(self):
        """小幻代理（国内）"""
        proxies = []
        try:
            req = urllib.request.Request(
                "https://ip.ihuan.me/today.html",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                matches = re.findall(r'(\d{1,3}(?:\.\d{1,3}){3})\s*:\s*(\d{2,5})', text)
                for host, port in matches:
                    proxies.append(f"http://{host}:{port}")
        except Exception:
            pass
        return proxies

    async def _fetch_ip3366(self):
        """云代理第1页（国内）"""
        return await self._fetch_ip3366_page("http://www.ip3366.net/free/?stype=1")

    async def _fetch_ip3366_page2(self):
        """云代理第2页"""
        return await self._fetch_ip3366_page("http://www.ip3366.net/free/?stype=2")

    async def _fetch_ip3366_page(self, url):
        """云代理通用解析"""
        proxies = []
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("gbk", errors="ignore")
                matches = re.findall(
                    r'<td[^>]*>(\d{1,3}(?:\.\d{1,3}){3})</td>\s*<td[^>]*>(\d{2,5})</td>',
                    text
                )
                for host, port in matches:
                    proxies.append(f"http://{host}:{port}")
        except Exception:
            pass
        return proxies

    # ==================== 代理验证 ====================

    async def fill_pool(self):
        """抓取代理 → TCP预筛 → HTTP验证，填充可用代理池"""
        raw_proxies = await self._fetch_proxies()
        if not raw_proxies:
            print("未能抓取到任何代理")
            return

        print(f"共 {len(raw_proxies)} 个候选，TCP 预筛选中...")

        # 第1步：TCP 连通性快速预筛（3秒超时）
        tcp_alive = []
        for proxy in raw_proxies:
            host, port = self._parse_proxy(proxy)
            if host and port:
                ok = await self._tcp_check(host, int(port), timeout=3)
                if ok:
                    tcp_alive.append(proxy)

        print(f"TCP 存活: {len(tcp_alive)}/{len(raw_proxies)}，开始 HTTP 验证...")

        if not tcp_alive:
            print("TCP 预筛后无可用代理")
            return

        # 第2步：HTTP 验证（更快，因为已经过了 TCP 筛选）
        session = await self._get_session()
        tasks = [asyncio.create_task(self._check_proxy(session, p)) for p in tcp_alive]

        valid = []
        for coro in asyncio.as_completed(tasks):
            proxy, ok = await coro
            if ok:
                valid.append(proxy)
                if len(valid) >= self.max_proxies:
                    break

        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.pool = deque(valid)
        print(f"验证完成，有效代理: {len(self.pool)}")

    @staticmethod
    def _parse_proxy(proxy):
        """从代理 URL 中解析 host 和 port"""
        proxy = proxy.replace("http://", "").replace("https://", "")
        if ":" in proxy:
            parts = proxy.split(":")
            return parts[0], parts[1]
        return None, None

    async def _tcp_check(self, host, port, timeout=3):
        """TCP 快速连通性检查"""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError):
            return False

    async def _check_proxy(self, session, proxy):
        """HTTP 验证代理是否真正可用"""
        async with self._semaphore:
            # 免费代理很多只支持 HTTP，不支持 HTTPS，用 HTTP 目标测试
            check_urls = [
                "http://www.baidu.com",
                "http://httpbin.org/ip",
                "http://pv.sohu.com/cityjson",
            ]
            for check_url in check_urls:
                try:
                    async with session.get(
                        check_url,
                        proxy=proxy,
                        timeout=10,
                        ssl=False,
                        allow_redirects=True,
                    ) as resp:
                        # 百度返回 200 但可能被代理改写，放宽判断
                        if resp.status in (200, 302, 301):
                            text = await resp.text()
                            if len(text) > 100:  # 确保有实质内容返回
                                return proxy, True
                except Exception:
                    continue
            return proxy, False

    # ==================== 代理操作 ====================

    def get(self):
        """取出一个代理（轮询）"""
        if not self.pool:
            return None
        proxy = self.pool.popleft()
        self.pool.append(proxy)
        return proxy

    def delete(self, proxy):
        """从池中移除指定代理"""
        try:
            self.pool.remove(proxy)
        except ValueError:
            pass

    async def validate_all(self):
        """验证池中所有代理，移除失效的"""
        if not self.pool:
            return
        session = await self._get_session()
        tasks = [self._check_proxy(session, proxy) for proxy in list(self.pool)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid = []
        for result in results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, tuple):
                proxy, ok = result
                if ok:
                    valid.append(proxy)

        self.pool = deque(valid)
        print(f"验证完成，有效代理: {len(self.pool)}")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


async def main():
    pool = ProxyPool(max_proxies=20)
    try:
        await pool.fill_pool()

        if pool.pool:
            print("\n可用代理列表：")
            for p in pool.pool:
                print(f"  {p}")
        else:
            print("\n未找到可用代理。免费代理存活率低，可稍后重试。")

    finally:
        await pool.close()


async def start_server(host="127.0.0.1", port=5010):
    """
    启动 HTTP API 服务：
      GET /get/       → 获取一个代理
      GET /delete/?proxy=xxx → 删除指定代理
      GET /pop/       → 弹出一个代理（不回放）
      GET /count/     → 返回池中代理数量
    """
    from aiohttp import web

    pool = ProxyPool(max_proxies=50)

    async def handle_get(request):
        proxy = pool.get()
        if proxy:
            return web.json_response({"proxy": proxy})
        return web.json_response({"proxy": None, "msg": "代理池为空"})

    async def handle_delete(request):
        proxy = request.query.get("proxy", "")
        if proxy:
            pool.delete(proxy)
            return web.json_response({"msg": f"已删除: {proxy}"})
        return web.json_response({"msg": "缺少 proxy 参数"}, status=400)

    async def handle_pop(request):
        if pool.pool:
            proxy = pool.pool.popleft()
            return web.json_response({"proxy": proxy})
        return web.json_response({"proxy": None, "msg": "代理池为空"})

    async def handle_count(request):
        return web.json_response({"count": len(pool.pool)})

    async def handle_index(request):
        return web.json_response({
            "endpoints": {
                "/get/": "获取一个代理",
                "/delete/?proxy=xxx": "删除指定代理",
                "/pop/": "弹出一个代理（不回放）",
                "/count/": "查看池中代理数量",
            }
        })

    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/get/", handle_get)
    app.router.add_get("/delete/", handle_delete)
    app.router.add_get("/pop/", handle_pop)
    app.router.add_get("/count/", handle_count)

    async def on_startup(app):
        await pool.fill_pool()
        print(f"\n[服务已启动] http://{host}:{port}")
        print(f"  获取代理: http://{host}:{port}/get/")
        print(f"  删除代理: http://{host}:{port}/delete/?proxy=xxx")
        print(f"  代理数量: http://{host}:{port}/count/")

    async def on_cleanup(app):
        await pool.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        print("正在启动代理池服务...")
        asyncio.run(start_server())
    else:
        asyncio.run(main())
