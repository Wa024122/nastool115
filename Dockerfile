FROM kleinersource/nastool

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir p115client==0.0.8.6.8 requests

COPY patches/cloud115_utils.py /nas-tools/app/utils/cloud115_utils.py
COPY patches/patch_nastool_cloud115.py /tmp/patch_nastool_cloud115.py
RUN python /tmp/patch_nastool_cloud115.py

ENV NASTOOL_AUTO_UPDATE=false
ENV CLOUD115_SRC_PREFIX=/root/NASTOOL/NASTOOL/nastool
ENV CLOUD115_REMOTE_SRC_ROOT=/nastool
