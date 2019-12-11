FROM python:3.6-alpine

ENV WORK_DIR=workdir \
  PAI_CONFIG_PATH=/etc/pai \
  PAI_LOGGING_PATH=/var/log/pai

ENV PAI_CONFIG_FILE=${PAI_CONFIG_PATH}/pai.conf \
  PAI_LOGGING_FILE=${PAI_LOGGING_PATH}/paradox.log

# build /opt/mqttwarn
RUN mkdir -p ${PAI_CONFIG_PATH} ${WORK_DIR} ${PAI_LOGGING_PATH}

# add user paradox to image
RUN addgroup pai && adduser -S pai -G pai
RUN chown -R pai ${WORK_DIR} ${PAI_LOGGING_PATH} ${PAI_CONFIG_PATH}

COPY --chown=pai . ${WORK_DIR}
COPY --chown=pai config/pai.conf.example ${PAI_CONFIG_PATH}/pai.conf

# OR
#RUN wget -c https://github.com/jpbarraca/pai/archive/master.tar.gz -O - | tar -xz --strip 1
#RUN wget -c https://raw.githubusercontent.com/jpbarraca/pai/master/config/pai.conf.example -O ${PAI_CONFIG_PATH}/pai.conf

# install python library
RUN cd ${WORK_DIR} \
  && pip install --no-cache-dir -r requirements.txt \
  && pip install . \
  && rm -fr ${WORK_DIR}

# process run as paradox user
USER pai

# conf file from host
VOLUME ${PAI_CONFIG_PATH}
VOLUME ${PAI_LOGGING_PATH}

# run process
CMD pai-service
