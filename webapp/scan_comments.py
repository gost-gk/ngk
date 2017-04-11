import logging
import time
import requests
import lxml.etree
import re
from schema import ScopedSession, SyncState


logging.basicConfig(
    filename="../logs/scan_comments.log",
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG)


COMMENTS_URL = "http://govnokod.ru/comments"
FAST_DELAY = 15
SLOW_DELAY = 60
FAST_TO_SLOW_STEPS = 20


def fetch_latest_comments():
    logging.debug("Fetching comments...")
    r = requests.get(COMMENTS_URL)
    r.raise_for_status()
    root = lxml.etree.HTML(r.content)

    comments = []
    for link in root.xpath('//a[@class="comment-link"]'):
        m = re.search("/([0-9]+)#comment([0-9]+)", link.get("href"))
        post_id = int(m.group(1))
        comment_id = int(m.group(2))
        comments.append((post_id, comment_id))

    return comments


def update_sync_states(comments):
    has_updates = False

    with ScopedSession() as session:
        for post_id, comment_id in comments:
            state = session.query(SyncState).filter(SyncState.post_id == post_id).one_or_none()
            if not state:
                logging.info("Got new comment %d for new post %d", comment_id, post_id)
                has_updates = True
                state = SyncState(post_id=post_id, last_comment_id=comment_id, pending=True, priority=SyncState.PRIORITY_HAS_COMMENTS)
                session.add(state)
            else:
                if comment_id > state.last_comment_id:
                    logging.info("Got new comment %d for post %d", comment_id, post_id)
                    has_updates = True
                    state.last_comment_id = comment_id
                    state.pending = True
                    state.priority=SyncState.PRIORITY_HAS_COMMENTS

    return has_updates

logging.info("=== started ===")

fast_requests = 0

while True:
    try:
        comments = fetch_latest_comments()
        has_updates = update_sync_states(comments)
        if has_updates:
            fast_requests = FAST_TO_SLOW_STEPS
    except Exception as e:
        logging.exception(e)
        fast_requests = 0

    if fast_requests > 0:
        delay = FAST_DELAY
        fast_requests -= 1
    else:
        delay = SLOW_DELAY

    logging.debug("Sleeping for %d seconds (%d fast requests left)...", delay, fast_requests)
    time.sleep(delay)
