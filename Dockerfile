FROM python:3.12-alpine
RUN apk add --no-cache iproute2
WORKDIR /app
COPY server.py /app/server.py
COPY static /app/static
ENV PYTHONUNBUFFERED=1 PORT=8090 DATA_DIR=/data
VOLUME /data
EXPOSE 8090
CMD ["python","/app/server.py"]
