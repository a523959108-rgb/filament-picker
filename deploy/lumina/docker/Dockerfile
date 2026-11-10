# 构建上下文由 build-image.sh 从同一份发布包创建，含已构建 frontend/dist。
FROM python:3.12-slim
ARG LUMINA_COMMIT
WORKDIR /app
COPY LUMINA_COMMIT /app/LUMINA_COMMIT
COPY _deploy/check-commit.sh /usr/local/lib/lumina/check-commit.sh
# 在安装任何系统/Python 依赖前拒绝空值、短 SHA 和版本不一致。
RUN bash /usr/local/lib/lumina/check-commit.sh "$LUMINA_COMMIT" /app/LUMINA_COMMIT
LABEL org.opencontainers.image.revision=$LUMINA_COMMIT \
      org.opencontainers.image.source="https://github.com/a523959108-rgb/filament-lumina"
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
COPY _deploy/deploy_support.py /usr/local/lib/lumina/deploy_support.py
RUN mkdir /tmp/lumina-deps \
    && python /usr/local/lib/lumina/deploy_support.py requirements requirements.txt /tmp/lumina-deps \
    && if [ -s /tmp/lumina-deps/torch.txt ]; then \
         python -m pip --isolated install --dry-run --report /tmp/lumina-deps/cpu.json \
           --index-url https://download.pytorch.org/whl/cpu -r /tmp/lumina-deps/torch.txt \
         && python /usr/local/lib/lumina/deploy_support.py report /tmp/lumina-deps/cpu.json \
         && python -m pip --isolated install --no-cache-dir \
           --index-url https://download.pytorch.org/whl/cpu -r /tmp/lumina-deps/torch.txt \
         && python -m pip --isolated freeze > /tmp/lumina-deps/constraints.txt; \
       else touch /tmp/lumina-deps/constraints.txt; fi \
    && python -m pip --isolated install --dry-run --report /tmp/lumina-deps/report.json \
       -c /tmp/lumina-deps/constraints.txt -r /tmp/lumina-deps/requirements.txt \
    && python /usr/local/lib/lumina/deploy_support.py report /tmp/lumina-deps/report.json \
    && python -m pip --isolated install --no-cache-dir \
       -c /tmp/lumina-deps/constraints.txt -r /tmp/lumina-deps/requirements.txt \
    && python -m pip check && rm -rf /tmp/lumina-deps
COPY . /app/
COPY _deploy/cleanup-output.sh /usr/local/bin/lumina-cleanup-output.sh
RUN groupadd --system lumina && useradd --system --gid lumina --home-dir /var/lib/lumina lumina \
    && mkdir -p /var/lib/lumina/materials /var/lib/lumina/cache /var/lib/lumina/output \
       /var/log/lumina /opt/lumina/shared/lut-preset /app/assets \
    && ln -s /var/lib/lumina/output /app/output \
    && ln -s /var/lib/lumina/materials /app/materials \
    && ln -s /var/log/lumina /app/logs \
    && for name in Custom Cloud _sync; do \
         mkdir -p /opt/lumina/shared/lut-preset/$name; \
         if [ -d /app/lut-preset/$name ]; then \
           cp -a /app/lut-preset/$name/. /opt/lumina/shared/lut-preset/$name/; \
           rm -rf /app/lut-preset/$name; fi; \
         ln -s /opt/lumina/shared/lut-preset/$name /app/lut-preset/$name; \
       done \
    && chown -R lumina:lumina /var/lib/lumina /var/log/lumina /opt/lumina/shared \
    && chown lumina:lumina /app/assets
ENV LUMINA_API_HOST=0.0.0.0 LUMINA_API_PORT=8790 LUMINA_SERVE_FRONTEND_DIST=1 \
    LUMINA_FRONTEND_DIST_DIR=/app/frontend/dist LUMINA_MATERIALS_DIR=/var/lib/lumina/materials \
    LUMINA_RUNTIME_CACHE_DIR=/var/lib/lumina/cache LUMINA_LOG_PATH=/var/log/lumina/lumina.jsonl \
    LUMINA_SETTINGS_PATH=/opt/lumina/shared/user_settings.json \
    LUMINA_WORKSHOP_DATA_DIR=/opt/lumina/shared/workshop \
    LUMINA_FEEDBACK_DUMP_DIR=/var/lib/lumina/output/feedback \
    NUMBA_CACHE_DIR=/var/lib/lumina/cache/numba XDG_CACHE_HOME=/var/lib/lumina/cache/xdg \
    XDG_DATA_HOME=/opt/lumina/shared/xdg LUMINA_MAX_WORKERS=4 \
    LUMINA_PREVIEW_CACHE_MAX_BYTES=268435456 CUDA_VISIBLE_DEVICES=-1 \
    PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
USER lumina
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8790/api/health',timeout=3)); assert d.get('status')=='ok' and d.get('worker_pool',{}).get('healthy') is True"
CMD ["python", "-B", "api_server.py"]
