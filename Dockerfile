FROM python:3.6

# build /opt/mqttwarn
RUN mkdir -p /opt/paradox
RUN git clone https://github.com/marcantoineveilleux/pai.git /opt/paradox
WORKDIR /opt/paradox

# install python library
RUN pip install -r requirements.txt

# add user paradox to image
RUN groupadd -r paradox && useradd -r -g paradox paradox
RUN chown -R paradox /opt/paradox

# process run as paradox user
USER paradox

# conf file from host
VOLUME ["/opt/paradox/config/user.py"]
VOLUME ["/opt/paradox/paradox.log"]

# run process
CMD python run.py