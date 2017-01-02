#!/bin/sh
set -e
set -x

chmod +x /sqlite_web/entrypoint.sh

if [ ${DEBUG} = "true" ] ; then
	cd /sqlite_web/sqlite_web
	python sqlite_web.py -d -H ${LISTEN_ADDRESS} -p ${LISTEN_PORT} -x ${DB_PATH}
else
	sqlite_web -H ${LISTEN_ADDRESS} -p ${LISTEN_PORT} -x ${DB_PATH}
	#cd /sqlite_web/sqlite_web
	# python sqlite_web.py -H ${LISTEN_ADDRESS} -p ${LISTEN_PORT} -x ${DB_PATH}
fi