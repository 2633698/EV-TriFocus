FROM python:3.9-slim

WORKDIR /app

# 安装matplotlib的系统依赖和中文字体
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libfreetype6-dev \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 设置matplotlib为非交互式后端并配置中文字体
ENV MPLBACKEND=Agg
ENV PYTHONIOENCODING=utf-8

COPY . .

# 创建目录
RUN mkdir -p output models

EXPOSE 5000

CMD ["python", "app.py"] 