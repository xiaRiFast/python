import winsound
import time


class 报警器:
    """简单蜂鸣报警器（基于 Windows winsound）"""

    @staticmethod
    def 蜂鸣(频率=1000, 时长=500):
        """
        发出指定频率和时长的蜂鸣声。
        参数:
            频率: Hz，默认 1000
            时长: 毫秒，默认 500
        """
        winsound.Beep(频率, 时长)

    @staticmethod
    def 短蜂鸣():
        """短促蜂鸣（1000Hz，200ms）"""
        winsound.Beep(1000, 200)

    @staticmethod
    def 长蜂鸣():
        """长蜂鸣（1000Hz，1000ms）"""
        winsound.Beep(1000, 1000)

    @staticmethod
    def 连续蜂鸣(次数=3, 间隔=0.2):
        """
        连续蜂鸣多次。
        参数:
            次数: 蜂鸣次数，默认 3
            间隔: 每次间隔秒数，默认 0.2
        """
        for _ in range(次数):
            winsound.Beep(1000, 300)
            time.sleep(间隔)

    @staticmethod
    def 紧急警报(时长=2):
        """
        高频紧急警报声（1500Hz，持续指定秒数，每秒响一次）。
        参数:
            时长: 持续秒数，默认 2
        """
        for _ in range(时长):
            winsound.Beep(1500, 500)
            time.sleep(0.5)


if __name__ == "__main__":
    print("测试短蜂鸣...")
    报警器.短蜂鸣()
    time.sleep(0.5)
    print("测试连续蜂鸣...")
    报警器.连续蜂鸣(3)
    time.sleep(0.5)
    print("测试紧急警报...")
    报警器.紧急警报(2)
