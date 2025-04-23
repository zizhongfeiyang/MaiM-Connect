FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /MaiMBot

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖列表和maim_message
COPY requirements.txt .
COPY maim_message /maim_message

# 安装Python依赖
RUN pip install --upgrade pip
RUN pip install -e /maim_message
RUN pip install -r requirements.txt

# 复制项目代码
COPY . .

# 创建必要的目录
RUN mkdir -p data logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

EXPOSE 8000

ENTRYPOINT ["python", "bot.py"]