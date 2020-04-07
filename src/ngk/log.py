import logging
import pathlib
import sys
from logging.handlers import RotatingFileHandler
from typing import IO, Optional, Union

from ngk import config


_FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(filename)s:%(lineno)d %(message)s', '%Y-%m-%d %H:%M:%S')
_FILE_EXT = '.log'


def _get_console_handler(stream: IO[str] = sys.stderr) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_FORMATTER)
    return handler


def _get_file_handler(filename: Union[pathlib.Path, str],
                      max_bytes: int = 1024*1024,
                      backup_count: int = 5) -> logging.Handler:
    handler = RotatingFileHandler(filename, mode='a', maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    handler.setFormatter(_FORMATTER)
    return handler


def _setup_basic_logging(level: int, stream: IO[str] = sys.stderr) -> None:
    console_handler = _get_console_handler(stream)
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.root.addHandler(console_handler)
    logging.root.setLevel(level)


def _add_log_extension(filename: str) -> str:
    if not filename.endswith(_FILE_EXT):
        filename += _FILE_EXT
    return filename


def get_logger(name: str,
               level: int,
               stream: IO[str] = sys.stderr,
               max_bytes: int = 1024*1024,
               backup_count: int = 5) -> logging.Logger:
    path = config.get_log_path(_add_log_extension(name))
    console_handler = _get_console_handler(stream)
    file_handler = _get_file_handler(path, max_bytes, backup_count)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger


def redirect_basic_logging(to_logger: logging.Logger, level: Optional[int]) -> None:
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    for handler in to_logger.handlers:
        logging.root.addHandler(handler)
    if level is None:
        level = to_logger.level
    logging.root.setLevel(level)


_setup_basic_logging(logging.WARNING)
