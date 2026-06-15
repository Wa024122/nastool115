FROM kleinersource/nastool

ADD https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.12.13%2B20260610-x86_64-unknown-linux-musl-install_only_stripped.tar.gz /tmp/python312.tar.gz

RUN mkdir -p /opt/python312 \
    && tar -xzf /tmp/python312.tar.gz -C /opt/python312 --strip-components=1 \
    && /opt/python312/bin/python3.12 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/python312/bin/python3.12 -m pip install --no-cache-dir p115client==0.0.8.6.8 requests \
    && rm -f /tmp/python312.tar.gz

COPY patches/cloud115_utils.py /nas-tools/app/utils/cloud115_utils.py
COPY patches/cloud115_worker.py /nas-tools/app/utils/cloud115_worker.py
COPY patches/cloud115.html /nas-tools/web/templates/cloud115.html
COPY patches/patch_nastool_cloud115.py /tmp/patch_nastool_cloud115.py
COPY patches/patch_nastool_cloud115_panel.py /tmp/patch_nastool_cloud115_panel.py
RUN python /tmp/patch_nastool_cloud115.py
RUN python /tmp/patch_nastool_cloud115_panel.py

ENV NASTOOL_AUTO_UPDATE=false
ENV CLOUD115_PYTHON=/opt/python312/bin/python3.12
ENV CLOUD115_SRC_PREFIX=/root/NASTOOL/NASTOOL/nastool
ENV CLOUD115_REMOTE_SRC_ROOT=/nastool
ENV CLOUD115_DEST_PREFIX=
ENV CLOUD115_REMOTE_DEST_ROOT=
