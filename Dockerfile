from python

COPY [".", "/sqlite_web"]

WORKDIR /sqlite_web

RUN pip install . && \
	chmod +x /sqlite_web/entrypoint.sh

WORKDIR /data

ENV DEBUG="false"
ENV LISTEN_PORT="80"
ENV LISTEN_ADDRESS="0.0.0.0"
ENV DB_PATH="/sqlite_web/sampledata/sample.sqlite"

entrypoint ["/sqlite_web/entrypoint.sh"]
