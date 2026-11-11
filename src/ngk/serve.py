"""
Production serving entrypoint: gevent PyWSGI via engineio's gevent runner.

Websockets are handled by simple-websocket.
"""

from decouple import config

from ngk.api import app, io


def main() -> None:
    host = config('SERVE_HOST', default='127.0.0.1')
    port = config('SERVE_PORT', default=30002, cast=int)
    io.run(app, host=host, port=port)


if __name__ == '__main__':
    main()
