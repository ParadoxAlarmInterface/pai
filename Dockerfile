FROM python:3.7-alpine

ENV WORK_DIR=workdir \
  HASSIO_DATA_PATH=/data \
  PAI_CONFIG_PATH=/etc/pai \
  PAI_LOGGING_PATH=/var/log/pai \
  PAI_MQTT_BIND_PORT=18839 \
  PAI_MQTT_BIND_ADDRESS=0.0.0.0

ENV PAI_CONFIG_FILE=${PAI_CONFIG_PATH}/pai.conf \
  PAI_LOGGING_FILE=${PAI_LOGGING_PATH}/paradox.log

RUN apk add --no-cache tzdata \
  && mkdir -p ${PAI_CONFIG_PATH} ${WORK_DIR} ${PAI_LOGGING_PATH}

COPY . ${WORK_DIR}
COPY config/pai.conf.example ${PAI_CONFIG_FILE}

# OR
#RUN wget -c https://github.com/jpbarraca/pai/archive/master.tar.gz -O - | tar -xz --strip 1
#RUN wget -c https://raw.githubusercontent.com/jpbarraca/pai/master/config/pai.conf.example -O ${PAI_CONFIG_PATH}/pai.conf

# install python library
RUN cd ${WORK_DIR} \
  && pip3 install --no-cache-dir -r requirements.txt \
  && pip3 install --no-cache-dir . \
  && rm -fr ${WORK_DIR}

# conf file from host
VOLUME ${PAI_CONFIG_PATH}
VOLUME ${PAI_LOGGING_PATH}
VOLUME ${HASSIO_DATA_PATH}

# For IP Interface
EXPOSE ${PAI_MQTT_BIND_PORT}/tcp
EXPOSE 10000/tcp

# run process
CMD pai-service
