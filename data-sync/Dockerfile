FROM python:3.12-slim
WORKDIR /app
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1
COPY app.py .
# 无 requirements（纯标准库）
CMD ["python", "app.py"]
