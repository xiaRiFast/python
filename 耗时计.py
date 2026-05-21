import time

"""耗时计"""
def 耗时装饰器(func):
	def inner(*可变参数, **关键字参数):
		起始时间 = time.time()
		装饰返回 = func(*可变参数, **关键字参数)
		耗时 = time.time() - 起始时间
		if 耗时 < 1:
			耗时 = f" {耗时*1000:.2f} 毫秒"
		else:
			耗时 = f" {耗时:.2f} 秒"
		print(f"耗时:{耗时}\n")
		return 装饰返回
	return inner

if __name__=="__main__":
	@耗时装饰器
	def abc():
		print("dddd")
		
	abc()
