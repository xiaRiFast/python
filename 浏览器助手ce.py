from playwright.sync_api import sync_playwright
import time
import os
from 耗时计 import 耗时装饰器 as 耗时
 
class 浏览器助手:
    """封装 Playwright 浏览器操作，使用无痕模式（非持久化），避免用户数据目录锁定问题"""

    def __init__(self, headless=False, viewport=None):
        self._playwright = None
        self.browser = None
        self.context = None
        self._page = None
        self.headless = headless

        # viewport 为 None 时自动获取屏幕分辨率
        if viewport is None:
            viewport = self._get_screen_size()
        self.viewport = viewport

        try:
            self._playwright = sync_playwright().start()
            # 使用无痕模式启动（不指定 user_data_dir，不会和系统Edge冲突）
            self.browser = self._playwright.chromium.launch(
                channel="msedge",
                headless=self.headless,
                args=["--no-first-run", "--no-default-browser-check", "--disable-extensions"]
            )
            self.context = self.browser.new_context(viewport=self.viewport)  # type: ignore
        except Exception as e:
            print(f"初始化浏览器失败: {e}")
            self.stop()
            raise

    @staticmethod
    def _get_screen_size():
        """获取主屏幕分辨率（使用 tkinter，无需第三方库）"""
        try:
            import tkinter as tk
            root = tk.Tk()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.destroy()
            return {"width": width, "height": height}
        except Exception:
            # 获取失败时回退到常见分辨率
            return {"width": 1920, "height": 1080}

    def stop(self):
        """安全停止浏览器"""
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
    @staticmethod
    def _escape_css_text(text: str) -> str:
        r"""
        转义 CSS 选择器中的 text 参数。
        Playwright :text-is() 和 :text() 内部使用 CSS 字符串，
        单引号 ' 和反斜杠 \ 需要转义，避免选择器语法错误。
        """
        return text.replace("\\", "\\\\").replace("'", "\\'")

    @耗时
    def 打开页面(self, url: str, timeout: int = 10000):
        """打开一个新标签页并导航到指定URL"""
        if not self.context:
            raise Exception("浏览器上下文未初始化或已关闭")

        self._page = self.context.new_page()
        try:
            self._page.goto(url, wait_until="load", timeout=timeout)
            print('打开标签页成功')
            return self._page
        except Exception as e:
            # 导航失败时关闭已创建的标签页，避免泄漏
            try:
                self._page.close()
            except:
                pass
            self._page = None
            raise Exception(f"打开页面失败 [{url}]: {e}")
    @耗时
    def 页面查找并点击(self, text: str, index=0):
        """在当前页面查找文字元素并点击，返回坐标信息"""
        if not self._page:
            raise Exception("当前没有打开的页面")

        safe = self._escape_css_text(text)
        selectors = [
            f"a:text-is('{safe}')",
            f"input[type='submit'][value='{safe}']",
            f"a:text('{safe}')",
            f"input[type='submit'][value*='{safe}']",
            f"button:text-is('{safe}')",
            f"button:text('{safe}')",
        ]

        elements = []
        for sel in selectors:
            try:
                elements = self._page.locator(sel).all()
                if elements:
                    break
            except:
                continue

        if not elements or index >= len(elements):
            print(f"未找到元素: {text}")
            return None

        elem = elements[index] #取出指定序号的元素
        bbox = elem.bounding_box() #获取元素的边界框（位置+大小）
        if not bbox: 
            print('这个元素不可见，直接放弃')
            return None

        info = {
            "文字": elem.text_content() or elem.get_attribute("value") or text,
            "x": bbox["x"],
            "y": bbox["y"],
            "width": bbox["width"],
            "height": bbox["height"],
            "中心点": {
                "x": bbox["x"] + bbox["width"] / 2,
                "y": bbox["y"] + bbox["height"] / 2,
            },
        }
        #info说明:{'文字': '返回游戏', 'x': 10, 'y': 202.3125, 'width': 68, 'height': 22, '中心点': {'x': 44.0, 'y': 213.3125}}

        print(f'info: {info}')

        # 记录点击前的标签页数量，用于检测是否弹出新标签页
        pages_before = len(self.context.pages) if self.context else 1

        # try:
        #     # 先尝试带导航等待的点击 导航（Navigation） = 浏览器从一个网页跳转到另一个网页的整个过程。
        #     with self._page.expect_navigation(wait_until="domcontentloaded", timeout=5000): #监听页面是否发生跳转最多等timeout秒
        #         elem.click()
        # except Exception as e:
            # 如果导航等待失败，尝试不带等待的点击
            # print(f"导航等待超时! 尝试直接点击: {e}")
        try:
            elem.click()
            # 等待页面进入稳定状态（domcontentloaded 不会死等，已加载完立即返回）
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception as retry_e:
            print(f"直接点击也失败! : {retry_e}")
            return None  # 点击失败，不继续后续操作

        print('点击了链接。')
        time.sleep(1.5)
        # 自动检测并切换到新弹出的标签页
        if self.context:
            pages_after = len(self.context.pages)
            if pages_after > pages_before:
                print(f"检测到弹出新标签页（{pages_before}→{pages_after}），自动切换...")
                self._page = self.context.pages[-1]
                # 等待新页面加载稳定
                try:
                    self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

        return info

    def 切换到最新标签页(self):
        """切换到浏览器上下文中最新的标签页（用于处理弹出新标签页的情况）"""
        if not self.context:
            return
        pages = self.context.pages
        if pages:
            self._page = pages[-1]  # 取最后一个（最新的）
            print(f"已切换到最新标签页，当前共 {len(pages)} 个标签页")

    def 关闭当前标签页(self):
        """关闭当前标签页，并自动切换到上一个标签页"""
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

    def 批量查找文字(self, text_list: list):
        """
        批量查找页面上的文字元素

        参数:
            text_list: 要查找的文字列表，如 ['小马', '嘎咕']

        返回:
            字典，以传入的文字为键，值为坐标信息或 None
            例如: {'小马': {'文字': '小马', 'x': 100, ...}, '嘎咕': None}
        """
        if not self._page:
            raise Exception("当前没有打开的页面")

        result = {}
        for text in text_list:
            info = self.查找文字(text)
            result[text] = info
        return result

    def 查找文字(self, text: str):
        """
        查找单个文字元素（支持链接、按钮、输入框、普通文字等所有类型），返回坐标信息（不点击）
        优先级：精确匹配 > 部分匹配
        """
        if not self._page:
            return None

        # 使用 Playwright 的 get_by_text 快速定位，避免 36 次单独查询
        # 先尝试精确匹配
        elem = self._page.get_by_text(text, exact=True).first
        if elem.count() == 0:
            # 精确未命中，尝试部分匹配
            elem = self._page.get_by_text(text, exact=False).first

        if elem.count() == 0:
            return None

        bbox = elem.bounding_box()
        if not bbox:
            return None

        # 获取标签名
        raw_tag = elem.evaluate("e => e.tagName")
        tag_map = {
            "A": "链接", "BUTTON": "按钮", "INPUT": "输入框",
            "SPAN": "行内文字", "DIV": "块级文字", "P": "段落",
            "TD": "表格单元", "LI": "列表项", "LABEL": "表单标签",
            "H1": "一级标题", "H2": "二级标题", "H3": "三级标题",
            "H4": "四级标题", "H5": "五级标题", "H6": "六级标题",
            "STRONG": "加粗文字", "EM": "斜体文字",
        }
        tag_cn = tag_map.get(raw_tag, raw_tag)

        return {
            "文字": (elem.text_content() or "").strip() or elem.get_attribute("value") or text,
            "标签": tag_cn,
            "x": bbox["x"],
            "y": bbox["y"],
            "width": bbox["width"],
            "height": bbox["height"],
            "中心点": {
                "x": bbox["x"] + bbox["width"] / 2,
                "y": bbox["y"] + bbox["height"] / 2,
            },
        }

class 查找:
    def 文字(self, text: str, 类型: str, page):
        """
        查找文字并打印结果。
        返回查找结果字典，若未找到或类型不匹配则返回 None。
        """
        r = page.查找文字(text)
        if r:
            print(f'查找文字成功：{r["文字"]} 类型：{r["标签"]} 中心坐标: {r["x"]},{r["y"]}')
            if 类型 and r['标签'] != 类型:
                print(f'类型不匹配（期望：{类型}，实际：{r["标签"]}）')
                return None
            return r
        else:
            print(f'查找文字 {text} 失败')
            return None

    def 文字和坐标(self, text: str, 类型: str, page):
        """
        查找文字，若成功且类型匹配，返回 (文字, x, y) 三元组。
        否则返回 False。
        """
        ret = self.文字(text, 类型, page)
        if ret:
            return ret['文字'], ret['x'], ret['y']
        return False
if __name__ == "__main__":
    助手 = None
    try:
        http = r"http://1.14.130.238:9999/gCmd.do?sid=k4lJVMtGTEwHFfic&cmd=2"
        http = r"https://www.163.com/"
        助手 = 浏览器助手()
        助手.打开页面(http)
        查找().文字("每日辟谣",'链接',助手)
        # time.sleep(1.5)
        # 助手.页面查找并点击("发展门户")
        # print("操作完成") 
        time.sleep(1.5)
        助手.页面查找并点击("每日辟谣")
        # print("操作完成")
        time.sleep(2.5)
        助手.页面查找并点击("郑州新密")
        # print("操作完成")
        time.sleep(2.5)

        # 批量查找文字示例
        结果 = 助手.批量查找文字(['行全网推送', '从总书记的改革'])
        print(结果)
        # {
        #   '小马': {'文字': '小马', 'x': 100, 'y': 200, '中心点': {...}},
        #   '嘎咕': {'文字': '嘎咕', 'x': 150, 'y': 250, '中心点': {...}},
        #   '不存在': None
        # }

    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        if 助手:
            助手.stop()
