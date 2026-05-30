# 风控可视化系统 - Docker 构建
FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 暴露端口
EXPOSE 8080

# 生产模式启动
ENV PRODUCTION=true
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "server.app:app"]
