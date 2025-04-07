import sys

# 将标准输出和标准错误重定向到文件
sys.stdout = open('test_output.txt', 'w')
sys.stderr = open('test_error.txt', 'w')

print("测试开始")

try:
    from ev_charging_scheduler import ChargingEnvironment, ChargingScheduler
    print("导入 ev_charging_scheduler 成功")
except Exception as e:
    print(f"导入 ev_charging_scheduler 失败: {str(e)}")

try:
    from ev_integration_scheduler import IntegratedChargingSystem
    print("导入 ev_integration_scheduler 成功")
except Exception as e:
    print(f"导入 ev_integration_scheduler 失败: {str(e)}")

try:
    from ev_multi_agent_system import MultiAgentSystem
    print("导入 ev_multi_agent_system 成功")
except Exception as e:
    print(f"导入 ev_multi_agent_system 失败: {str(e)}")

print("测试结束")

# 关闭重定向的文件
sys.stdout.close()
sys.stderr.close()

# 恢复标准输出和标准错误
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

print("测试完成，请查看test_output.txt和test_error.txt文件") 