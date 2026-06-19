FROM python:3.14-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget unzip ca-certificates libicu72 git \
    build-essential autoconf automake libtool pkg-config \
    && rm -rf /var/lib/apt/lists/*

# .NET 9 runtime for EZ Tools
RUN wget -q https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 9.0 --runtime dotnet --install-dir /usr/share/dotnet \
    && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet \
    && rm /tmp/dotnet-install.sh

COPY scripts/install-eztools-linux.sh scripts/eztools-checksums.sha256 /tmp/
RUN chmod +x /tmp/install-eztools-linux.sh && EZTOOLS_ROOT=/opt/eztools bash /tmp/install-eztools-linux.sh

COPY scripts/fetch-sigma-rules.sh /usr/local/bin/fetch-sigma-rules.sh
COPY scripts/fetch-chainsaw-rules.sh /usr/local/bin/fetch-chainsaw-rules.sh
COPY scripts/fetch-yara-rules.sh /usr/local/bin/fetch-yara-rules.sh
COPY scripts/install-chainsaw.sh /usr/local/bin/install-chainsaw.sh
RUN chmod +x /usr/local/bin/fetch-sigma-rules.sh /usr/local/bin/fetch-chainsaw-rules.sh /usr/local/bin/fetch-yara-rules.sh /usr/local/bin/install-chainsaw.sh \
    && /usr/local/bin/fetch-sigma-rules.sh /opt/sigma-bundled \
    && /usr/local/bin/fetch-chainsaw-rules.sh /opt/chainsaw-bundled \
    && /usr/local/bin/fetch-yara-rules.sh /opt/yara-bundled/signature-base \
    && /usr/local/bin/install-chainsaw.sh /usr/local/bin/chainsaw
COPY apps/worker/yara/zz_smoketest.yar /opt/yara-bundled/signature-base/yara/zz_smoketest.yar

COPY scripts/install-hindsight.sh /usr/local/bin/install-hindsight.sh
# RyanDFIR/hindsight release v2026.04 (pinned for reproducible builds)
ARG HINDSIGHT_REF=f64bd92e8297244e923b5bba880a46fba4974402
RUN chmod +x /usr/local/bin/install-hindsight.sh \
    && HINDSIGHT_REF=${HINDSIGHT_REF} /usr/local/bin/install-hindsight.sh

COPY scripts/install-open-forensics.sh /usr/local/bin/install-open-forensics.sh
ARG INSTALL_OPEN_FORENSICS=false
ARG INSTALL_VOLATILITY3=false
RUN chmod +x /usr/local/bin/install-open-forensics.sh \
    && if [ "${INSTALL_OPEN_FORENSICS}" = "true" ]; then \
        INSTALL_VOLATILITY3="${INSTALL_VOLATILITY3}" /usr/local/bin/install-open-forensics.sh; \
      fi

COPY third_party/licenses /licenses
COPY THIRD_PARTY_NOTICES.md /licenses/THIRD_PARTY_NOTICES.md

COPY scripts/docker-worker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY packages/corvus_core /app/packages/corvus_core
RUN pip install --no-cache-dir /app/packages/corvus_core

COPY apps/worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/worker /app/apps/worker
ENV PYTHONPATH=/app/apps/worker
ENV EZTOOLS_ROOT=/opt/eztools
ENV SIGMA_RULES_ROOT=/opt/sigma/rules
ENV SIGMA_RULES_BUNDLED=/opt/sigma-bundled
ENV CHAINSAW_RULES_ROOT=/opt/chainsaw/rules
ENV CHAINSAW_RULES_BUNDLED=/opt/chainsaw-bundled
ENV CHAINSAW_MAPPINGS_ROOT=/opt/chainsaw/mappings
ENV CHAINSAW_BIN=/usr/local/bin/chainsaw
ENV CHAINSAW_ENABLED=true
ENV YARA_RULES_ROOT=/opt/yara/rules
ENV YARA_RULES_BUNDLED=/opt/yara-bundled/signature-base
ENV YARA_ENABLED=true
ENV HINDSIGHT_ENABLED=true
ENV HINDSIGHT_BIN=/usr/local/bin/hindsight
ENV PATH=/opt/open-forensics/bin:${PATH}
ENV HOME=/home/app

# Run as a non-root user with the same uid as the api service so the shared
# evidence_data volume and the rule volumes get consistent ownership when first
# created. The worker writes rule bundles, the DFIR cache, and the YARA seed
# under /opt/{sigma,chainsaw,yara}, so those roots are owned by the app user.
RUN groupadd -g 10001 app && useradd -u 10001 -g 10001 -m app \
    && mkdir -p /data/evidence /opt/sigma/rules /opt/chainsaw/rules /opt/chainsaw/mappings /opt/yara/rules \
    && chown -R 10001:10001 /data/evidence /opt/sigma /opt/chainsaw /opt/yara /home/app
USER app

WORKDIR /app/apps/worker
ENTRYPOINT ["/entrypoint.sh"]
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "-Q", "ingest"]
