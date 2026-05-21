from playwright.sync_api import sync_playwright
import time
import os
from 耗时计 import 耗时装饰器 as 耗时
import 配置设置
from 报警 import 报警器
设置 = 配置设置.设置()


class 浏览器助手:
    """封装 Playwright 浏览器操作，使用无痕模式（非持久化），避免用户数据目录锁定问题"""

    def __init__(self, headless=False, viewport=None, 浏览器类型="chromium", 通道=None):
        """
        初始化浏览器助手，启动指定浏览器（无痕模式）。

        参数：
            headless:     是否无头运行（不显示窗口），默认 False
            viewport:     窗口分辨率字典 {"width": int, "height": int}，
                          为 None 时自动获取屏幕分辨率
            浏览器类型:    浏览器引擎，可选 "chromium"（默认）"firefox" "webkit"
            通道:         仅 chromium 有效，指定系统已安装的浏览器，
                          可选 "chrome""msedge" 等，默认 None（使用内置 Chromium）

        返回：
            无（构造函数）

        异常：
            初始化失败时会打印错误并抛出异常
        """
        self._playwright = None
        self.browser = None
        self.context = None
        self._page = None
        self.headless = headless
        self._上次点击时间 = 0

        # viewport 为 None 时自动获取屏幕分辨率
        if viewport is None:
            viewport = self._get_screen_size()
        self.viewport = viewport

        try:
            self._playwright = sync_playwright().start()
            # 使用无痕模式启动（不指定 user_data_dir，不会和系统Edge冲突）
            if 浏览器类型 == "chromium":
                self.browser = self._playwright.chromium.launch(
                    headless=self.headless,
                    channel=通道,
                    args=[
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-extensions",
                    ],
                )
            elif 浏览器类型 == "firefox":
                self.browser = self._playwright.firefox.launch(headless=self.headless)
            elif 浏览器类型 == "webkit":
                self.browser = self._playwright.webkit.launch(headless=self.headless)
            else:
                raise ValueError(f"不支持的浏览器类型: {浏览器类型}")
            self.context = self.browser.new_context(viewport=self.viewport)  # type: ignore
        except Exception as e:
            print(f"初始化浏览器失败: {e}")
            self.stop()
            raise

    @staticmethod
    def _get_screen_size():
        """
        获取主屏幕分辨率。

        返回：
            {"width": int, "height": int}  分辨率字典
            获取失败时回退返回 {"width": 1920, "height": 1080}
        """
        try:
            import tkinter as tk

            root = tk.Tk()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.destroy()
            return {"width": width, "height": height}
        except Exception:
            return {"width": 1920, "height": 1080}

    def stop(self):
        """
        安全停止浏览器，依次关闭页面、上下文、浏览器和 Playwright。

        返回：
            无
        """
        if self._page:
            try:
                self._page.close()
            except:
                pass
            self._page = None
        if self.context:
            try:
                self.context.close()
            except:
                pass
            self.context = None
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
            self.browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except:
                pass
            self._playwright = None

    def _等待点击间隔(self):
        """确保两次点击之间至少间隔 设置.通用等待 秒，不足则补足"""
        间隔 = time.time() - self._上次点击时间
        if 间隔 < 设置.通用等待:
            补偿 = 设置.通用等待 - 间隔
            time.sleep(补偿)
        self._上次点击时间 = time.time()

    @staticmethod
    def _escape_css_text(text: str) -> str:
        """
        转义 CSS 选择器中的 text 参数，避免单引号和反斜杠破坏选择器语法。

        参数：
            text: 原始文字内容

        返回：
            str —— 转义后的安全字符串
        """
        return text.replace("\\", "\\\\").replace("'", "\\'")

    @耗时
    def 打开页面(self, url: str, timeout: int = 10000):
        """
        打开一个新标签页并导航到指定 URL。

        参数：
            url:     目标网页地址
            timeout: 页面加载超时时间（毫秒），默认 10000（10秒）

        返回：
            Page 对象（Playwright 页面对象）

        异常：
            打开失败时抛出 Exception，并自动关闭已创建的标签页
        """
        if not self.context:
            raise Exception("浏览器上下文未初始化或已关闭")

        self._page = self.context.new_page()
        try:
            self._page.goto(url, wait_until="load", timeout=timeout)
            print("打开标签页成功")
            return self._page
        except Exception as e:
            try:
                self._page.close()
            except:
                pass
            self._page = None
            raise Exception(f"打开页面失败 [{url}]: {e}")

    @耗时
    def 查找并点击(self, text: str, index=0, 精确=True, 调试=False, 绕过确认=False):
        """
        在当前页面查找文字元素并点击，返回坐标信息。
        使用 JS 遍历所有元素和文本节点，选最精确匹配的。

        参数：
            text:   要查找的文字内容
            index:  同文字元素中第几个（从0开始），默认取第一个
            精确:    是否只精确匹配，默认 False（先精确后模糊）
            绕过确认: 是否自动绕过 confirm/alert 弹框，默认 False

        返回：
            点击成功时返回字典：
            {
                "文字": str,
                "标签": str,
                "x": float, "y": float,
                "width": float, "height": float,
                "中心点": {"x": float, "y": float}
            }
            未找到元素、元素不可见或点击失败时返回 None
        """
        if not self._page:
            raise Exception("当前没有打开的页面")
        if not text:
            print("⚠️ 查找文字为空，跳过点击")
            return None
        if 绕过确认:
            self._page.evaluate("window.confirm = function() { return true; }")

        # 用 JS 查找所有匹配元素（和查找文字同一套逻辑），返回候选列表
        candidates = self._page.evaluate("""({text, exactOnly}) => {
            const interactive = new Set(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']);
            const results = [];
            const tags = 'a,button,input,span,td,li,label,h1,h2,h3,h4,h5,h6,strong,em,div,p';

            for (const node of document.querySelectorAll(tags)) {
                const raw = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                const val = (node.value || '').trim();
                const matchText = raw || val;
                if (!matchText) continue;

                const exact = matchText === text;
                const partial = !exact && matchText.includes(text);
                if (exactOnly) {
                    if (!exact) continue;
                } else {
                    if (!exact && !partial) continue;
                }

                const rect = node.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                results.push({
                    len: matchText.length,
                    exact: exact ? 0 : 1,
                    isInteractive: interactive.has(node.tagName) ? 0 : 1,
                    isTextNode: 1,
                    tag: node.tagName,
                    text: matchText,
                    value: val,
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                });
            }

            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            let textNode;
            while (textNode = walker.nextNode()) {
                const raw = textNode.textContent.replace(/\\s+/g, ' ').trim();
                if (!raw) continue;

                const exact = raw === text;
                const partial = !exact && raw.includes(text);
                if (exactOnly) {
                    if (!exact) continue;
                } else {
                    if (!exact && !partial) continue;
                }

                const range = document.createRange();
                range.selectNodeContents(textNode);
                const rect = range.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                results.push({
                    len: raw.length,
                    exact: exact ? 0 : 1,
                    isInteractive: 2,
                    isTextNode: 0,
                    tag: '#text',
                    text: raw,
                    value: '',
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                });
            }

            results.sort((a, b) => {
                if (a.isTextNode !== b.isTextNode) return a.isTextNode - b.isTextNode;
                if (a.exact !== b.exact) return a.exact - b.exact;
                if (a.isInteractive !== b.isInteractive) return a.isInteractive - b.isInteractive;
                return a.len - b.len;
            });

            return results;
        }""", {"text": text, "exactOnly": 精确})

        if not candidates or index >= len(candidates):
            print(f"未找到元素: {text}")
            return None

        best = candidates[index]
        tag_map = {
            "#text": "纯文本",
            "A": "链接", "BUTTON": "按钮", "INPUT": "输入框",
            "SPAN": "行内文字", "DIV": "块级文字", "P": "段落",
            "TD": "表格单元", "LI": "列表项", "LABEL": "表单标签",
            "H1": "一级标题", "H2": "二级标题", "H3": "三级标题",
            "H4": "四级标题", "H5": "五级标题", "H6": "六级标题",
            "STRONG": "加粗文字", "EM": "斜体文字",
        }

        info = {
            "文字": best["text"] or best["value"] or text,
            "标签": tag_map.get(best["tag"], best["tag"]),
            "x": best["x"],
            "y": best["y"],
            "width": best["width"],
            "height": best["height"],
            "中心点": {
                "x": best["x"] + best["width"] / 2,
                "y": best["y"] + best["height"] / 2,
            },
        }
        if 调试:
            print(f"info: {info}")

        # 记录点击前的标签页数量，用于检测是否弹出新标签页
        pages_before = len(self.context.pages) if self.context else 1

        try:
            self._等待点击间隔()
            self._page.click(f"text={text}", timeout=5000)
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception as retry_e:
            print(f"点击失败! : {retry_e}")
            return None

        print("点击了链接。")
        # 自动检测并切换到新弹出的标签页
        if self.context:
            pages_after = len(self.context.pages)
            if pages_after > pages_before:
                print(
                    f"检测到弹出新标签页（{pages_before}→{pages_after}），自动切换..."
                )
                self._page = self.context.pages[-1]
                try:
                    self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

        return info

    def 切换到最新标签页(self):
        """
        切换到浏览器上下文中最新的标签页。

        返回：
            无
        """
        if not self.context:
            return
        pages = self.context.pages
        if pages:
            self._page = pages[-1]  # 取最后一个（最新的）
            print(f"已切换到最新标签页，当前共 {len(pages)} 个标签页")

    def 关闭当前标签页(self):
        """
        关闭当前标签页，并自动切换到上一个标签页。

        返回：
            无
        """
        if not self._page or not self.context:
            return
        pages = self.context.pages
        current_index = pages.index(self._page) if self._page in pages else -1

        # 先确定切换目标（在 close 之前保存引用，避免列表变更后索引失效）
        next_page = None
        if len(pages) > 1 and current_index > 0:
            next_page = pages[current_index - 1]
        elif len(pages) > 1:
            next_page = pages[-1]  # 关闭第一个时切到最后一个

        self._page.close()
        self._page = next_page

    def 批量查找文字(self, text_list: list, 精确=True):
        """
        批量查找页面上的文字元素。

        参数：
            text_list: 要查找的文字列表，如 ["小马", "嘎咕"]
            精确:       是否只精确匹配，默认 False（先精确后模糊）

        返回：
            字典，以传入的文字为键，值为坐标信息或 None
            例如：
            {
                "小马": {"文字": "小马", "标签": "链接", "x": 100.0, ...},
                "嘎咕": None
            }
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        result = {}
        for text in text_list:
            info = self.查找文字(text, 精确=精确)
            result[text] = info
        return result

    @耗时
    def 点击文字后的链接(self, 前置文字: str, index: int = 0, 精确=True):
        """
        找到页面上包含指定文字的位置，然后点击紧跟在它后面的第 N 个链接。

        适用场景：
            "你遇到 <a>黑色棕熊</a> 、 <a>花斑豹子</a>"
            → 点击文字后的链接("你遇到", 0) 点击第一个怪

        参数：
            前置文字:  在页面上定位的文字，如 "你遇到"
            index:    点击后面的第几个链接（从0开始），默认第一个
            精确:      是否精确匹配前置文字，默认 False（模糊匹配）

        返回：
            点击成功返回字典 {"文字": str, "标签": "链接", ...}
            未找到或点击失败返回 None

        示例：
            # 点击"你遇到"后面的第一个怪（模糊匹配，默认）
            助手.点击文字后的链接("你遇到")
            # 精确匹配"你遇到"三个字
            助手.点击文字后的链接("你遇到", 精确=True)
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        result = self._page.evaluate("""({text, index, exactOnly}) => {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            let node;
            while (node = walker.nextNode()) {
                const raw = node.textContent.replace(/\\s+/g, ' ').trim();
                if (!raw) continue;
                const matched = exactOnly ? (raw === text) : raw.includes(text);
                if (!matched) continue;

                // 找到前置文字，从它后面的节点开始找 <a> 标签
                const parent = node.parentElement;
                const allLinks = parent.querySelectorAll('a');
                // 收集在该文本节点之后的链接
                const linksAfter = [];
                for (const a of allLinks) {
                    // 比较位置：链接在文本节点之后
                    const cmp = node.compareDocumentPosition(a);
                    if (cmp & Node.DOCUMENT_POSITION_FOLLOWING) {
                        linksAfter.push(a);
                    }
                }
                if (index >= linksAfter.length) return { found: false, total: linksAfter.length };
                const target = linksAfter[index];
                const rect = target.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return { found: false, total: linksAfter.length };
                return {
                    found: true,
                    total: linksAfter.length,
                    text: (target.textContent || '').trim(),
                    href: target.href || '',
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                };
            }
            return { found: false, total: 0 };
        }""", {"text": 前置文字, "index": index, "exactOnly": 精确})

        if not result or not result.get("found"):
            total = result.get("total", 0) if result else 0
            print(f"在'{前置文字}'后面未找到第 {index} 个链接（共找到 {total} 个）")
            return None

        info = {
            "文字": result["text"],
            "标签": "链接",
            "x": result["x"],
            "y": result["y"],
            "width": result["width"],
            "height": result["height"],
            "中心点": {
                "x": result["x"] + result["width"] / 2,
                "y": result["y"] + result["height"] / 2,
            },
        }
        # print(f"info: {info}")

        pages_before = len(self.context.pages) if self.context else 1
        try:
            self._等待点击间隔()
            self._page.click(f"text={result['text']}", timeout=5000)
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception as e:
            print(f"点击失败! : {e}")
            return None

        print(f"点击了链接: {result['text']}")

        if self.context:
            pages_after = len(self.context.pages)
            if pages_after > pages_before:
                print(f"检测到弹出新标签页（{pages_before}→{pages_after}），自动切换...")
                self._page = self.context.pages[-1]
                try:
                    self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

        return info

    def 查找文字(self, text: str, 精确=True):
        """
        查找单个文字元素，返回坐标信息（不点击）。
        使用 JS 遍历页面所有元素和文本节点，选最精确匹配的。
        优先级：完全相等 > 交互标签(a/button/input) > 文本长度最短

        参数：
            text:  要查找的文字内容
            精确:   是否只精确匹配，默认 False（先精确后模糊）
                    设为 True 时，只返回 text_content 完全等于目标文字的元素

        返回：
            查找成功时返回字典：
            {
                "文字": str,
                "标签": str,
                "x": float, "y": float,
                "width": float, "height": float,
                "中心点": {"x": float, "y": float}
            }
            未找到或元素不可见时返回 None
        """
        if not self._page:
            return None
        if not text:
            print("⚠️ 查找文字为空，跳过")
            return None

        # 用 JS 遍历所有元素 + 文本节点，找最精确的那个
        result = self._page.evaluate("""({text, exactOnly}) => {
            const interactive = new Set(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']);
            const candidates = [];
            const tags = 'a,button,input,span,td,li,label,h1,h2,h3,h4,h5,h6,strong,em,div,p';

            // 1. 遍历有标签的元素
            for (const node of document.querySelectorAll(tags)) {
                const raw = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                const val = (node.value || '').trim();
                const matchText = raw || val;
                if (!matchText) continue;

                const exact = matchText === text;
                const partial = !exact && matchText.includes(text);
                if (exactOnly) {
                    if (!exact) continue;
                } else {
                    if (!exact && !partial) continue;
                }

                const rect = node.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                candidates.push({
                    len: matchText.length,
                    exact: exact ? 0 : 1,
                    isInteractive: interactive.has(node.tagName) ? 0 : 1,
                    isTextNode: 1,
                    tag: node.tagName,
                    text: matchText,
                    value: val,
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                });
            }

            // 2. 遍历裸文本节点（处理没有标签包裹的文字，如 <br/>请选择方向<br/>）
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            let textNode;
            while (textNode = walker.nextNode()) {
                const raw = textNode.textContent.replace(/\\s+/g, ' ').trim();
                if (!raw) continue;

                const exact = raw === text;
                const partial = !exact && raw.includes(text);
                if (exactOnly) {
                    if (!exact) continue;
                } else {
                    if (!exact && !partial) continue;
                }

                // 用 Range 获取文本节点的屏幕坐标
                const range = document.createRange();
                range.selectNodeContents(textNode);
                const rect = range.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                candidates.push({
                    len: raw.length,
                    exact: exact ? 0 : 1,
                    isInteractive: 2,
                    isTextNode: 0,
                    tag: '#text',
                    text: raw,
                    value: '',
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                });
            }

            if (!candidates.length) return null;

            // 排序：文本节点 > 完全相等 > 交互标签 > 文本越短
            candidates.sort((a, b) => {
                if (a.isTextNode !== b.isTextNode) return a.isTextNode - b.isTextNode;
                if (a.exact !== b.exact) return a.exact - b.exact;
                if (a.isInteractive !== b.isInteractive) return a.isInteractive - b.isInteractive;
                return a.len - b.len;
            });

            const best = candidates[0];
            return {
                tag: best.tag, text: best.text, value: best.value,
                x: best.x, y: best.y,
                width: best.width, height: best.height
            };
        }""", {"text": text, "exactOnly": 精确})

        if not result:
            return None

        tag_map = {
            "#text": "纯文本",
            "A": "链接", "BUTTON": "按钮", "INPUT": "输入框",
            "SPAN": "行内文字", "DIV": "块级文字", "P": "段落",
            "TD": "表格单元", "LI": "列表项", "LABEL": "表单标签",
            "H1": "一级标题", "H2": "二级标题", "H3": "三级标题",
            "H4": "四级标题", "H5": "五级标题", "H6": "六级标题",
            "STRONG": "加粗文字", "EM": "斜体文字",
        }
        tag_cn = tag_map.get(result["tag"], result["tag"])

        return {
            "文字": result["text"] or result["value"] or text,
            "标签": tag_cn,
            "x": result["x"],
            "y": result["y"],
            "width": result["width"],
            "height": result["height"],
            "中心点": {
                "x": result["x"] + result["width"] / 2,
                "y": result["y"] + result["height"] / 2,
            },
        }

    def 截图区域(
        self,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        保存路径: str | None = None,
        全页面: bool = False,
    ):
        """
        截取页面并保存为图片。
        如果不传坐标和宽高，默认截取整个页面（或完整长页面）。

        参数：
            x:          区域左上角 x 坐标，默认 None（不裁剪）
            y:          区域左上角 y 坐标，默认 None（不裁剪）
            width:      区域宽度，默认 None（不裁剪）
            height:     区域高度，默认 None（不裁剪）
            保存路径:   截图保存的文件路径，默认自动生成带时间的名称，如 "截图12_05.png"
            全页面:     是否截取完整长页面，默认 False（截取当前可视区域）
                        注意：全页面与 clip 区域不能同时生效

        返回：
            保存路径（str）

        异常：
            当前没有打开页面时抛出 Exception
        """
        if not self._page:
            raise Exception("当前没有打开的页面，无法截图")

        if 保存路径 is None:
            保存路径 = f"截图{time.strftime('%H_%M_%S')}.png"

        if x is not None and y is not None and width is not None and height is not None:
            self._page.screenshot(
                path=保存路径, clip={"x": x, "y": y, "width": width, "height": height}
            )
            print(f"截图已保存: {保存路径} ({width}x{height} @ {x},{y})")
        else:
            self._page.screenshot(path=保存路径, full_page=全页面)
            模式 = "完整页面" if 全页面 else "当前可视区域"
            print(f"截图已保存: {保存路径} ({模式})")
        return 保存路径

    def 截图元素(self, text: str, 保存路径: str | None = None):
        """
        查找指定文字元素并截取该元素所在区域。

        参数：
            text:       要查找的文字内容
            保存路径:   截图保存的文件路径，默认自动生成带时间的名称，如 "元素截图12_05.png"

        返回：
            保存路径（str）

        异常：
            未找到元素或元素不可见时抛出 Exception
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        if 保存路径 is None:
            保存路径 = f"元素截图{time.strftime('%H_%M')}.png"

        elem = self._page.get_by_text(text, exact=True).first
        if elem.count() == 0:
            elem = self._page.get_by_text(text, exact=False).first
        if elem.count() == 0:
            raise Exception(f"未找到文字元素: {text}")

        bbox = elem.bounding_box()
        if not bbox:
            raise Exception(f"元素 '{text}' 不可见，无法截图")

        self._page.screenshot(path=保存路径, clip=bbox)
        print(
            f"元素截图已保存: {保存路径} ({bbox['width']}x{bbox['height']} @ {bbox['x']},{bbox['y']})"
        )
        return 保存路径

    def 获取页面片段(self, 选择器: str = "body") -> str:
        """
        获取页面指定区域的 HTML 文本内容。

        参数：
            选择器:  CSS 选择器，默认 "body"（整个页面主体）

        返回：
            该元素内部的 HTML 文本（str），未找到时返回空字符串

        示例：
            html = 助手.获取页面片段("#content")
            print(html[:500])  # 打印前 500 个字符
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        elem = self._page.locator(选择器).first
        if elem.count() == 0:
            print(f"未找到选择器对应的元素: {选择器}")
            return ""

        return elem.inner_html()

    def 获取按br分段文本(self, 选择器: str = "body") -> list:
        """
        获取指定元素内按 <br> 分段的纯文本列表。

        参数：
            选择器:  CSS 选择器，默认 "body"

        返回：
            每段纯文本的列表（已去掉 HTML 标签和首尾空白）

        示例：
            段落 = 助手.获取按br分段文本("div")
            for 行 in 段落:
                print(行)
        """
        import re

        html = self.获取页面片段(选择器)
        if not html:
            return []

        # 按 <br> / <br/> / <br /> 拆分
        parts = re.split(r"<br\s*/?>", html, flags=re.IGNORECASE)
        result = []
        for part in parts:
            # 去掉所有 HTML 标签，只保留文字
            text = re.sub(r"<[^>]+>", "", part)
            text = text.strip()
            if text:
                result.append(text)
        return result

    def 填写输入框(self, 选择器: str, 内容: str, 清空: bool = True):
        """
        在页面指定的输入框中填写内容。

        参数：
            选择器:  CSS 选择器，例如 "input[name='username']"
            内容:    要填入的文字
            清空:    是否先清空原有内容，默认 True

        返回：
            无

        示例：
            助手.填写输入框("input[name='username']", "admin")
            助手.填写输入框("input[type='password']", "123456")
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        elem = self._page.locator(选择器).first
        if elem.count() == 0:
            raise Exception(f"未找到输入框: {选择器}")

        # 确保元素在可视区域并聚焦（不用 click，避免触发页面的点击拦截）
        elem.scroll_into_view_if_needed()
        elem.focus()
        time.sleep(0.3)

        if 清空:
            elem.fill(内容)
        else:
            elem.type(内容, delay=50)

        # 验证是否真正写进去了
        实际值 = elem.input_value()
        if 实际值 != 内容:
            print(f"⚠️ 填写可能未生效，当前值: '{实际值}'，期望值: '{内容}'")
        else:
            print(f"✅ 已填写输入框 {选择器}: {内容}")

    def 提交表单(self, 选择器: str = "form"):
        """
        提交页面上的表单（按回车或找到提交按钮点击）。

        参数：
            选择器:  CSS 选择器，默认 "form"（页面第一个表单）

        返回：
            无
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        form = self._page.locator(选择器).first
        if form.count() == 0:
            raise Exception(f"未找到表单: {选择器}")

        # 先尝试找表单内的提交按钮点击
        submit = form.locator("input[type='submit'], button[type='submit']").first
        if submit.count() > 0:
            self._等待点击间隔()
            submit.click()
            print("已点击表单提交按钮")
        else:
            # 没有提交按钮则按回车提交
            form.press("Enter")
            print("已按回车提交表单")

        # 等待页面加载稳定
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass

class 查找:
    """页面元素查找辅助类，封装常用查找操作。"""

    def 文字(self, text: str, 类型: str, page):
        """
        查找文字并打印结果。

        参数：
            text:  要查找的文字内容
            类型:  期望的元素类型（标签中文名），传空字符串则不校验类型
                   可选值：
                     "链接"        —— <a>
                     "按钮"        —— <button>
                     "输入框"      —— <input>
                     "行内文字"    —— <span>
                     "块级文字"    —— <div>
                     "段落"        —— <p>
                     "表格单元"    —— <td>
                     "列表项"      —— <li>
                     "表单标签"    —— <label>
                     "一级标题" ~ "六级标题" —— <h1> ~ <h6>
                     "加粗文字"    —— <strong>
                     "斜体文字"    —— <em>
            page:  浏览器助手实例

        返回：
            查找成功时返回字典：
            {
                "文字": "实际文字内容",
                "标签": "链接",               # 元素类型中文名
                "x": 10.0, "y": 202.3,       # 元素左上角坐标
                "width": 68, "height": 22,   # 元素宽高
                "中心点": {"x": 44.0, "y": 213.3}  # 元素中心坐标
            }
            未找到或类型不匹配时返回 None。

        示例：
            结果 = 查找().文字("每日辟谣", "链接", 助手)
            if 结果:
                print(结果["中心点"])  # 可用来获取中心坐标
        """
        r = page.查找文字(text)
        if r:
            print(
                f'查找文字成功：{r["文字"]} 类型：{r["标签"]} 中心坐标: {r["x"]},{r["y"]}'
            )
            if 类型 and r["标签"] != 类型:
                print(f'类型不匹配（期望：{类型}，实际：{r["标签"]}）')
                return None
            return r
        else:
            print(f"查找文字 {text} 失败")
            return None

    def 文字和坐标(self, text: str, 类型: str, page):
        """
        查找文字，若成功且类型匹配，返回 (文字, x, y) 三元组。

        参数：同 文字() 方法。

        返回：
            成功时返回 (文字内容, x坐标, y坐标)，例如：
                ("每日辟谣", 44.0, 213.3)
            失败时返回 False。

        示例：
            结果 = 查找().文字和坐标("每日辟谣", "链接", 助手)
            if 结果:
                文字, x, y = 结果
                print(f"在 ({x}, {y}) 找到 '{文字}'")
        """
        ret = self.文字(text, 类型, page)
        if ret:
            return ret["文字"], ret["x"], ret["y"]
        return False

def 随机等待(最小=0.23, 最大=0.3):
    """随机等待指定秒数范围，模拟人工操作间隔"""
    import random
    time.sleep(random.uniform(最小, 最大))   
    
class 重启异常(Exception):
    """用于通知外层循环重新初始化主程序（调试器不会断开）"""
    pass

class 常用:
    def 确定要在主页(self,助手:浏览器助手):
        """
        用于正常流程
        """
        r2 = 助手.查找文字('请选择行走的方向')
        if r2:
            if r2['文字']:

                print(f'检测当前在主页成功!')
                return True
        else:
            r = 助手.查找并点击('返回游戏') 
            
            if r is None:
                print(f'警告: 当前不在主页,尝试查找返回游戏,也没有找到!')
            else:
                print('提醒: 当前不在主页,尝试查找返回游戏,补救成功!')
                return True  
        print('警告: 检测__当前在主页失败!!')
        self.返回游戏主页(助手)

    def 导航去一个地方(self,助手:浏览器助手, 搜索目的地 = 设置.目的地):
        r = 助手.查找并点击('导航')
        if r:
            print('点击导航成功!')
            随机等待()
            r = self.输入框输入点搜索按钮(助手,输入内容=搜索目的地)
            if r:
                print(f'搜索目的地{搜索目的地}成功!!!')
                r = 助手.查找并点击(搜索目的地, 绕过确认=True)
                if r:
                    print('点击目的地链接成功!应该已经到了新的地方')  
                    return True                                    
                else:
                    print('点击目的地链接失败!!!')
                    助手.截图区域(全页面=True) 
                    return False      
            else:
                print('搜索目的地失败!!!')
                助手.截图区域(全页面=True) 
                return False 
        else:
            print('点击导航失败!!')
            助手.截图区域(全页面=True)   
            return False

    def 去休息一下再来(self,助手:浏览器助手,返回地=设置.目的地):
        """
        去客栈休息再回来
        """   
        休息时间 = 20 #秒
        #点击导航
        r = 助手.查找并点击('导航')
        if r:
            print('休息:点导航成功!')
            r = 助手.查找并点击('长安',精确=True,绕过确认=True)
            if r:
                print('点击[长安]成功,应该到了客栈,马上休息')
                xr = 助手.查找文字('休息',精确=True)
                随机等待(设置.通用等待)
                if xr:
                    print('找到休息')
                    限时 = time.time()
                    while time.time() - 限时 <= 休息时间 and xr is True: 
                        xr = 助手.查找并点击('休息')
                        随机等待(1.5,2)

                    print('休息完毕!,马上回去打工')

        r = self.导航去一个地方(助手,搜索目的地=返回地)
        if r:
            print(f'成功返回到刷怪地点 {返回地}')
        else:
            print('警告: 导航系统混乱,没有成功送达!!!!重启')
            self.重启本脚本()

    def 输入框输入点搜索按钮(self, 助手: 浏览器助手, 输入内容: str = "", 输入框选择器: str = "input[type='text']", 搜索按钮文字: str = "搜索"):
        """
        在页面输入框填入内容后点击搜索按钮。

        参数:
            输入内容:      要填入输入框的文本
            输入框选择器:   定位输入框的 CSS 选择器，默认取第一个文本输入框
            搜索按钮文字:   搜索按钮上显示的文字，默认 "搜索"

        返回:
            成功返回 True，失败返回 False
        """
        if not 输入内容:
            print("错误: 输入内容为空")
            return False

        try:
            助手.填写输入框(输入框选择器, 输入内容)
        except Exception as e:
            print(f"错误: 填写输入框失败: {e}")
            return False

        r = 助手.查找并点击(搜索按钮文字)
        if r is None:
            print(f"错误: 点击搜索按钮 '{搜索按钮文字}' 失败")
            return False

        print(f"成功: 已输入 '{输入内容}' 并点击搜索")
        return True



    def 返回游戏主页(self,助手:浏览器助手):
        """
        一般用于预期外的情况
        """
        
        r = 助手.查找并点击('返回游戏')
        if r is None:
            print('提醒: 返回游戏主页__操作失败!')
            #检测是否在进行什么
            r = 助手.查找并点击('察看')
            if r is None:
                print('警告: 检测__也不是在进行中的战斗界面!!')
            else:
                print('居然是战斗中界面!!!马上延续战斗//')
                r = 战斗页面(助手)
                if r:
                    print('成功续接//战斗,成功完成!')
                else:
                    print('续接战斗也失败!!!!')
        else:
            print('成功: 操作__点击_[游戏主页]成功!')
        self.重启本脚本()

    def 重启本脚本(self):
        """抛出重启异常，由外层循环捕获后重新初始化主程序（调试器不会断开）"""
        print('准备重启脚本...')
        报警器.紧急警报(2)
        raise 重启异常()
    
def 战斗页面(助手:浏览器助手):

    #首次等待

    开始t = time.time()
    print(f'..战斗中..: 首次等待 = {设置.战斗首次等待}')
    随机等待(设置.战斗首次等待,设置.战斗首次等待+0.1)    
    第一次点察看 = True
    计数 = 0

    while time.time()-开始t < 15:
        r = 助手.查找并点击('察看')
        if r is None:
            if 第一次点察看:
                print('警告: 操作__点击_"察看"第一次失败!!')
                return False
            else:
                print('提醒: 战斗可能结束_! 马上退出循环')
                break
        第一次点察看 = False
        计数 += 1
        随机等待(设置.察看等待-0.03,设置.察看等待+0.03)

    print(f'---------\n战斗结算: 共点击察看 {计数} 次 耗时: {(time.time()-开始t):.2f} 秒\n==============\n')     
    return True

def 登录游戏(
    助手: 浏览器助手,
    网站=r"http://1.14.130.238:9999/login",
    用户名=None,
    密码=None,
):
    """
    打开登录页并自动填写账号密码提交。
    用户名/密码不传则自动读取 配置设置 模块。
    """
    if 用户名 is None:
        用户名 = 设置.用户
    if 密码 is None:
        密码 = 设置.密码

    助手.打开页面(网站, timeout=10000)

    # 等待页面稳定（WAP 老页面有时需要多等一会）
    time.sleep(0.6)


    # 填用户名
    if 用户名:
        助手.填写输入框("input[name='username']", 用户名)
    else:
        while True:
            print("⚠️ 用户名为空!!!!!!!!!!!!!")
            报警器.长蜂鸣()
            time.sleep(1)

    # 填密码
    if 密码:
        助手.填写输入框("input[name='password']", 密码)
    else:
        while True:
            print("⚠️ 密码为空!!!!!!!!!!!!")
            报警器.长蜂鸣()
            time.sleep(1)        

    # 提交方式：直接点“登录游戏”按钮更可靠
    time.sleep(0.5)
    try:
        助手.查找并点击("登录游戏")
    except Exception as e:
        print(f"点击登录按钮失败，尝试表单提交: {e}")
        助手.提交表单("form")

    print("登录提交完成")
    time.sleep(0.7)

    片段html = 助手.获取按br分段文本()
    print(f"br:---------------\n {片段html[:3]}")

    #检测是否成功登录
    r = 助手.查找文字('欢迎您回来',精确=False)
    if r is None:
        while True:
            print(f'警告: 登录后没有出现欢迎您!!!!!!')
            报警器.连续蜂鸣()
            time.sleep(2)

    r = 助手.查找并点击('一区',精确=False)
    if r is None:
        while True:
            print(f'错误: 点击 "一区" 失败!!!!!!!!!!')
            报警器.连续蜂鸣()
            time.sleep(2)


    r = 助手.查找并点击('开始游戏',精确=False)
    if r is None:
        while True:        
            print(f'错误: 点击 "开始游戏" 失败!')
            报警器.连续蜂鸣()
            time.sleep(2)
    常用().确定要在主页(助手)


    # ========== 开始登录 ==========


# async function 登录游戏() {
#   console.log('\n========== 开始登录 ==========');

#   console.time('  获取首页');
#   let 首页源码 = await 安全请求(基础网址);
#   console.timeEnd('  获取首页');
#   if (!首页源码) { console.log('× 首页获取失败'); return null; }

#   await 模块.sleepAsync(1500);

#   console.log('正在提交登录信息...');
#   let 登录结果 = await 模块.submitForm(基础网址, 首页源码, {
#     username: 配置.username,
#     password: 配置.password
#   });
#   if (!登录结果) { console.log('× 登录失败'); return null; }

#   console.log('√ 登录成功！');
#   await 模块.sleepAsync(1500);

#   let 页面 = await 点击链接(登录结果, '一区');
#   if (!页面) { console.log('× 进入一区失败'); return null; }

#   await 模块.sleepAsync(500);

#   页面 = await 点击链接(页面, '开始游戏');
#   if (!页面) { console.log('× 开始游戏失败'); return null; }

#   return 页面;
# }


def 打怪升级(助手: 浏览器助手):

    登录游戏(助手)
    打怪次数 = 0
    初始时间 = time.time()
    while True:


        print('检测是否在主页..')
        常用().确定要在主页(助手)


        #主页检测怪有没有
        r = 助手.查找文字('你遇到')
        if r is None:
            print(f'提醒: 检测__[你遇到]失败!')
            r = 助手.查找并点击('刷新')
            if r:
                print('提醒: 操作__点击_[刷新]成功!')
            else:
                print('警告: 操作__点击_[刷新]失败!!')
                常用().返回游戏主页(助手)
        else:
            print('成功: 检测__[你遇到]成功!')


        #主页点击怪
        r = 助手.点击文字后的链接('你遇到',0)
        if r is None:
            print('警告: 操作__点击__[你遇到]后面链接[怪物]失败!')
            常用().返回游戏主页(助手)
        else:
            print('成功: 操作__点击_[你遇到]后面链接[怪物]成功!')


        #列表检测目标怪
        最终目标 = ''
        r = 助手.批量查找文字([设置.第一目标,设置.第二目标],精确=True)
        if r is None:
            print('警告: 检测__[目标怪]返回了空字典!!!!!!!')
            常用().返回游戏主页(助手)
        else:
            if r[设置.第一目标]:
                print(f'成功: 检测__找到第一目标!')
                最终目标 = 设置.第一目标
            elif r[设置.第二目标]:
                print(f'成功: 检测__找到第二目标!')   
                最终目标 = 设置.第二目标
            else:
                print(f'警告: 检测__第一与第二目标都没找到!!')      

        #列表操作点击最终目标
        r = 助手.查找并点击(最终目标,精确=False)
        if r is None:
            print('警告: 操作__点击_最终目标失败!')
            常用().返回游戏主页(助手)
        else:
            print('成功: 操作__点击_最终目标成功!')    

        
        #面板检测是否是玩家,检测是否出现'玩家判断'
        r = 助手.查找文字(设置.玩家判断)
        if r is None:
            print('安全: 检测__该目标是非玩家!')
        else:
            while True:
                print('危险: 检测__这是一个玩家!!')
                报警器.蜂鸣()
                time.sleep(2)

        #面板点击杀戮
        r = 助手.查找并点击('杀戮')
        if r is None:
            print('警告: 操作__点击_[杀戮]失败!!')
            常用().返回游戏主页(助手)
        else:
            print('成功: 操作__点击_[杀戮]成功!')

        #检测是否是非可攻击
        r = 助手.查找文字('这里不允许发生战斗')
        if r is None:
            print('成功: 检测__非可攻击成功!')
        else:
            #可点击返回游戏
            while True:
                print('警告: 检测__非可攻击失败!!!!:这里不允许发生战斗:')  
                报警器.蜂鸣()
                time.sleep(2)

        #战斗页
        r = 助手.查找文字('察看')
        if r is None:  
            print('警告: 检测__"察看"首次失败!') 
            常用().返回游戏主页(助手)     
        else:
            print('成功: ...=>进入战斗<= ...')

        r = 战斗页面(助手)
        if r is None:
            print('警告: 操作__点击_察看首次都失败!!')
            常用().返回游戏主页(助手) 
        else:
            打怪次数 += 1
            print(f'打怪次数={打怪次数}')
        #检测逃跑
        r = 助手.查找文字(设置.逃跑提示)
        if r is None:
            print('安全: 检测__No逃跑字样"^_^')
        else:
            print('警告: 检测__出现"逃跑"##!!')
            常用().去休息一下再来(助手,返回地=设置.目的地)

        本怪耗时 = round((time.time()-初始时间),2)
        print(f'本怪耗时:{本怪耗时},打怪次数={打怪次数}')
            
if __name__ == "__main__":
    主循环i = 0
    重启记录 = []           # 存储每次重启的时间戳
    时间窗口秒 = 120        # 分钟
    最大重启次数 = 3        # 窗口内允许的最大重启次数

    while True:
        助手 = None
        try:
            助手 = 浏览器助手(
                headless=False, viewport={"width": 600, "height": 850}, 通道="chrome"
            )

            打怪升级(助手)
            主循环i += 1
            print(f"======= __main__主循环第 {主循环i} ======")

        except 重启异常:
            print("捕获重启信号，正在重新初始化...")
            if 助手:
                助手.stop()

            现在 = time.time()
            重启记录.append(现在)
            # 清理窗口外的旧记录
            重启记录 = [t for t in 重启记录 if 现在 - t <= 时间窗口秒]

            if len(重启记录) > 最大重启次数:
                print(f"报警: {时间窗口秒} 秒内重启 {len(重启记录)} 次，超过阈值 {最大重启次数}，停止运行!")
                from 报警 import 报警器
                报警器.连续蜂鸣(5)
                break
            continue

        except Exception as e:
            print(f"发生错误: {e}")
            break

        finally:
            if 助手:
                助手.stop()
    报警器.短蜂鸣()
    print('运行停止')