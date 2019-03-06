FROM python:3.6

# build /opt/mqttwarn
RUN mkdir -p /etc/pai
RUN mkdir -p /opt/pai
RUN mkdir -p /opt/log
RUN git clone https://github.com/jpbarraca/pai.git /opt/pai
WORKDIR /opt/pai

RUN cp /opt/pai/config/pai.conf.example /etc/pai/pai.conf

# install python library
RUN pip install -r requirements.txt

# add user paradox to image
RUN groupadd -r paradox && useradd -r -g paradox paradox
RUN chown -R paradox /opt/pai
RUN chown -R paradox /opt/log
RUN chown -R paradox /etc/pai

# process run as paradox user
USER paradox

# conf file from host
VOLUME ["/etc/pai/pai.conf"]
VOLUME ["/opt/log/"]

# run process
CMD python run.py
