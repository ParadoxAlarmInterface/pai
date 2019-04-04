FROM python:3.6-alpine

# build /opt/mqttwarn
RUN mkdir -p /etc/pai
RUN mkdir -p /opt/pai
RUN mkdir -p /opt/log

RUN apk add git

RUN git clone https://github.com/jpbarraca/pai.git /opt/pai
WORKDIR /opt/pai

RUN cp /opt/pai/config/pai.conf.example /etc/pai/pai.conf

# install python library
RUN pip install -r requirements.txt

# add user paradox to image
RUN addgroup pai && adduser -S pai -G pai
RUN chown -R pai /opt/pai
RUN chown -R pai /opt/log
RUN chown -R pai /etc/pai

# process run as paradox user
USER pai

# conf file from host
VOLUME ["/etc/pai/"]
VOLUME ["/opt/log/"]

# run process
CMD python run.py
