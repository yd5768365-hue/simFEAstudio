FROM ubuntu:24.04

# System deps: Python, solvers, nginx, supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    calculix-ccx gmsh \
    nginx supervisor curl \
    && rm -rf /var/lib/apt/lists/*

# Python backend
WORKDIR /app
COPY pyproject.toml .
COPY src/backends/ src/backends/
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -e .

# Frontend (pre-built locally)
COPY dist /app/frontend

# Workspace for run archives
RUN mkdir -p /workspace/.simfea/runs /workspace/.simfea/learning

# Nginx: serve frontend on :3000, proxy API to :8008
COPY docker/nginx.conf /etc/nginx/conf.d/simfea.conf
RUN rm -f /etc/nginx/sites-enabled/default

# Supervisor: run nginx + sidecar
COPY docker/supervisord.conf /etc/supervisor/conf.d/simfea.conf

EXPOSE 3000
VOLUME ["/workspace"]
ENV SIMFEA_HOME=/workspace

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
