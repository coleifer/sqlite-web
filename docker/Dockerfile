FROM coleifer/sqlite
RUN pip install --no-cache-dir cython && pip install --no-cache-dir flask peewee sqlite-web
EXPOSE 8080
VOLUME /data
WORKDIR /data
CMD sqlite_web -H 0.0.0.0 -x $SQLITE_DATABASE
