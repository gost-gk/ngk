import logging

from ngk import config
from ngk.log import get_logger
from ngk.comments_processor import CommentsProcessor


L = get_logger('comments_listener', logging.DEBUG)


def main() -> None:
    processor = CommentsProcessor(config.REDIS_HOST,
                                config.REDIS_PORT,
                                config.REDIS_PASSWORD,
                                config.REDIS_CHANNEL,
                                L)
    processor.subscribe()
    for x in processor.listen():
        print(len(x))
