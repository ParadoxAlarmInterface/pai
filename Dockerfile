FROM python:3.15-slim-trixie AS base

RUN apt-get update \
  && apt-get install -y --no-install-recommends tzdata libffi8 libgcc-s1 libssl3t64 \
  && rm -rf /var/lib/apt/lists

FROM base AS builder

# CFFI may need a C compiler on ARMv7; cryptography must use a prebuilt wheel.
RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc libc6-dev libffi-dev \
  && rm -rf /var/lib/apt/lists

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=cryptography -r requirements.txt

COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY paradox ./paradox
RUN pip install --no-cache-dir --only-binary=cryptography .

FROM base AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
  HASSIO_DATA_PATH=/data \
  PAI_CONFIG_PATH=/etc/pai \
  PAI_LOGGING_PATH=/var/log/pai \
  PAI_MQTT_BIND_PORT=18839 \
  PAI_MQTT_BIND_ADDRESS=0.0.0.0

ENV PAI_CONFIG_FILE=${PAI_CONFIG_PATH}/pai.conf \
  PAI_LOGGING_FILE=${PAI_LOGGING_PATH}/paradox.log

RUN mkdir -p ${PAI_CONFIG_PATH} ${PAI_LOGGING_PATH}

COPY --from=builder /opt/venv /opt/venv
COPY config/pai.conf.example ${PAI_CONFIG_FILE}

RUN python -c "import _cffi_backend; from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes; Cipher(algorithms.AES(bytes(16)), modes.ECB()).encryptor().finalize()"

# conf file from host
VOLUME ${PAI_CONFIG_PATH}
VOLUME ${PAI_LOGGING_PATH}
VOLUME ${HASSIO_DATA_PATH}

# For IP Interface
EXPOSE ${PAI_MQTT_BIND_PORT}/tcp
EXPOSE 10000/tcp

# run process
CMD ["pai-service"]
