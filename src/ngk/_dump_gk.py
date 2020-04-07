import decimal
import logging
import os
import os.path
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import lxml.etree
import lxml.html
import requests

from ngk import config
from ngk.schema import Comment, Post, ScopedSession, SyncState, User


logging.basicConfig(
    filename=config.get_log_path('dump_gk.log'),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG)


SUCCESS_DELAY = 8
ERROR_DELAY = 30

    
def generate_tasks() -> None:
    if len(sys.argv) != 3:
        print('Usage: {} <start post id> <end post id>'.format(sys.argv[0]))
        sys.exit(1)
    
    logging.info("=== started ===")
    start_id = int(sys.argv[1])
    end_id = int(sys.argv[2])

    for post_id in range(start_id, end_id + 1):
        try:
            with ScopedSession() as session:
                state = session.query(SyncState).filter(SyncState.post_id == post_id).one_or_none()
                if not state:
                    logging.info("Dumping new post %d", post_id)
                    state = SyncState(post_id=post_id, pending=True, priority=SyncState.PRIORITY_DUMP)
                    session.add(state)
                else:
                    logging.info("Updating post %d", post_id)
                    state.pending = True
                    state.priority=SyncState.PRIORITY_DUMP
            delay = SUCCESS_DELAY
        except Exception as e:
            logging.exception(e)
            delay = ERROR_DELAY
        time.sleep(delay)
    logging.info("=== dumping done ===")


generate_tasks()
