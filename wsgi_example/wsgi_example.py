# Example showing how to run sqlite-web with a different WSGI server.
from gevent import monkey ; monkey.patch_all()
from gevent.pool import Pool
from gevent.pywsgi import WSGIServer

import os
import sys

# Put sqlite_web on our python-path.
cur_dir = os.path.dirname(__file__)
sys.path.insert(0, os.path.realpath(os.path.join(cur_dir, '../sqlite_web')))

from sqlite_web import app
from sqlite_web import configure_app


def main():
    pool = Pool(50)
    kwargs = configure_app()

    # Get host and port from config.
    bind_address = (kwargs.pop('host'), kwargs.pop('port'))

    server = WSGIServer(bind_address, app, log=None, spawn=pool)
    server.serve_forever()


if __name__ == '__main__':
    main()
