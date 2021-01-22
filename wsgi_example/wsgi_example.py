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
from sqlite_web import initialize_app


def main(db_file):
    initialize_app(db_file)
    pool = Pool(50)
    server = WSGIServer(('127.0.0.1', 8080), app, log=None, spawn=pool)
    server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('missing required database file.')
        sys.exit(1)

    main(sys.argv[1])
