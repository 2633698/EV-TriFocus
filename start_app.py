"""
启动脚本 - 确保正确启动Flask应用
"""
import os
import sys
import subprocess
import webbrowser
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("startup.log")
    ]
)
logger = logging.getLogger("StartupScript")

def main():
    """启动应用"""
    try:
        logger.info("启动EV充电调度模拟系统...")
        
        # 确保output目录存在
        if not os.path.exists("output"):
            os.makedirs("output")
            logger.info("创建output目录")
        
        # 确保配置文件存在
        if not os.path.exists("config.json"):
            logger.error("找不到config.json文件!")
            return
        
        logger.info("启动Flask应用...")
        
        # 使用subprocess启动Flask应用
        flask_process = subprocess.Popen([sys.executable, "app.py"],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         universal_newlines=True)
        
        logger.info("等待Flask应用启动...")
        time.sleep(2)  # 给应用一些启动时间
        
        if flask_process.poll() is not None:
            # 如果进程已结束，输出错误信息
            logger.error("Flask应用启动失败!")
            stdout, stderr = flask_process.communicate()
            logger.error(f"标准输出:\n{stdout}")
            logger.error(f"标准错误:\n{stderr}")
            return
        
        # 打开浏览器
        logger.info("在浏览器中打开应用...")
        webbrowser.open("http://localhost:5000")
        
        logger.info("应用已启动，请在浏览器中使用")
        logger.info("按Ctrl+C停止应用")
        
        # 保持脚本运行，将Flask输出传递给控制台
        while True:
            output = flask_process.stdout.readline()
            if output:
                print(output.strip())
            
            error = flask_process.stderr.readline()
            if error:
                print(f"ERROR: {error.strip()}", file=sys.stderr)
            
            if flask_process.poll() is not None:
                break
            
            time.sleep(0.1)
        
        logger.info("应用已停止")
    
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭应用...")
        if 'flask_process' in locals():
            flask_process.terminate()
    
    except Exception as e:
        logger.error(f"启动过程中发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main() 