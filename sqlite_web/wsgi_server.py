from gevent import monkey ; monkey.patch_all()
from gevent.pool import Pool
from gevent.pywsgi import WSGIServer

import os
import sys

# Put sqlite_web on our python-path.
checkout = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.realpath(checkout))

from sqlite_web.sqlite_web import app
from sqlite_web.sqlite_web import configure_app


def main():
    pool = Pool(50)
    kwargs = configure_app()

    # Get host and port from config.
    bind_address = (kwargs.pop('host'), kwargs.pop('port'))

    server_kwargs = {}
    if kwargs.get('ssl_context') is not None:
        from werkzeug.serving import generate_adhoc_ssl_context
        from werkzeug.serving import load_ssl_context

        pair = kwargs['ssl_context']
        if pair == 'adhoc':
            ssl_ctx = generate_adhoc_ssl_context()
        else:
            ssl_ctx = load_ssl_context(*pair)

        server_kwargs['ssl_context'] = ssl_ctx

    print('Serving on %s:%s' % bind_address)

    server = WSGIServer(bind_address, app, log=None, spawn=pool,
                        **server_kwargs)
    server.serve_forever()


if __name__ == '__main__':
    main()
