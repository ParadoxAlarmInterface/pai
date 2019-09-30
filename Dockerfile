ARG ARCH=""
# RPI ARCH="arm32v7/"

FROM ${ARCH}python:3.6-alpine3.10

ENV PAI_BASE_DIR=/usr/local/pai \
  PAI_CONFIG_PATH=/etc/pai \
  PAI_LOGGING_PATH=/var/log/pai

ENV PAI_CONFIG_FILE=${PAI_CONFIG_PATH}/pai.conf \
  PAI_LOGGING_FILE=${PAI_LOGGING_PATH}/paradox.log

# build /opt/mqttwarn
RUN mkdir -p ${PAI_CONFIG_PATH} ${PAI_BASE_DIR} ${PAI_LOGGING_PATH}

WORKDIR ${PAI_BASE_DIR}

# add user paradox to image
RUN addgroup pai && adduser -S pai -G pai
RUN chown -R pai ${PAI_BASE_DIR} ${PAI_LOGGING_PATH} ${PAI_CONFIG_PATH}

ADD --chown=pai paradox ${PAI_BASE_DIR}/paradox
ADD --chown=pai requirements.txt ${PAI_BASE_DIR}/requirements.txt
ADD --chown=pai run.py ${PAI_BASE_DIR}/run.py
ADD --chown=pai config/pai.conf.example ${PAI_CONFIG_PATH}/pai.conf

# OR
#RUN wget -c https://github.com/jpbarraca/pai/archive/master.tar.gz -O - | tar -xz --strip 1
#RUN wget -c https://raw.githubusercontent.com/jpbarraca/pai/master/config/pai.conf.example -O ${PAI_CONFIG_PATH}/pai.conf

# install python library
RUN pip install --no-cache-dir -r requirements.txt

# process run as paradox user
USER pai

# conf file from host
VOLUME ${PAI_CONFIG_PATH}
VOLUME ${PAI_LOGGING_PATH}

# run process
CMD python run.py
