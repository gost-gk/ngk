import atexit
import datetime
import logging
import re
import signal
import threading
import time
from typing import List, Sequence, Tuple

import lxml
import lxml.etree
import requests

from comments_processor import CommentsProcessor
import config
from html_util import inner_html_ru, normalize_text
from parse_error import ParseError
import parser_xyz
from schema import Comment, CommentIdStorage, ScopedSession, SyncState


logging.basicConfig(
    filename="../logs/scan_comments.log",
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO)


COMMENTS_URL = 'http://govnokod.ru/comments'
COMMENTS_URL_XYZ = 'https://govnokod.xyz/comments/'
FAST_DELAY = 15
SLOW_DELAY = 60
FAST_TO_SLOW_STEPS = 20

GK_GUEST8_ID = 25580

exit_event = threading.Event()
threads_exited_events: List[threading.Event] = []


def fetch_latest_comments() -> List[Tuple[int, int, str]]:
    logging.debug("Fetching comments from ru...")
    r = requests.get(COMMENTS_URL, headers=config.DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    root = lxml.etree.HTML(r.content)

    comments: List[Tuple[int, int, str]] = []
    for comment_entry in root.xpath('//li[@class="hcomment"]'):
        comment_link = comment_entry.xpath('.//a[@class="comment-link"]')[0]
        m = re.search("/([0-9]+)#comment([0-9]+)", comment_link.get("href"))
        if m is None:
            raise ParseError('Invalid comment-link (no regex match)')
        post_id = int(m.group(1))
        comment_id = int(m.group(2))
        comment_text = normalize_text(inner_html_ru(comment_entry.xpath('.//div[@class="entry-comment"]')[0]))
        comments.append((post_id, comment_id, comment_text))

    return comments


def fetch_latest_comments_xyz() -> List[parser_xyz.CommentXyz]:
    logging.debug("Fetching comments from xyz...")
    r = requests.get(COMMENTS_URL_XYZ, headers=config.DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    root = lxml.etree.HTML(r.content)
    return parser_xyz.parse_comments(root)


def update_sync_states(comments: Sequence[Tuple[int, int, str]], processor: CommentsProcessor):
    has_updates = False
    updated_comments: List[Comment] = []
    with ScopedSession() as session:
        for post_id, comment_id, comment_text in comments:
            comment_db = session.query(Comment).filter(Comment.comment_id == comment_id).first()
            if comment_db is not None and comment_db.text != comment_text:
                comment_db.text = comment_text
                updated_comments.append(comment_db)

            state = session.query(SyncState).filter(SyncState.post_id == post_id).one_or_none()
            if not state:
                logging.info("Got new comment %d for new post %d", comment_id, post_id)
                has_updates = True
                state = SyncState(post_id=post_id, last_comment_id=comment_id, pending=True, priority=SyncState.PRIORITY_HAS_COMMENTS)
                session.add(state)
            else:
                if state.last_comment_id is None or comment_id > state.last_comment_id:
                    logging.info("Got new comment %d for post %d", comment_id, post_id)
                    has_updates = True
                    state.last_comment_id = comment_id
                    state.pending = True
                    state.priority=SyncState.PRIORITY_HAS_COMMENTS

        if len(updated_comments) > 0:
            logging.info(f'Fast-fetched {len(updated_comments)} updated ' + \
                         f'comment{"s" if len(updated_comments) > 1 else ""}: {[c.comment_id for c in updated_comments]}')
            session.commit()
            processor.on_comments_update([], updated_comments)

    return has_updates


def update_xyz_states(comments: Sequence[parser_xyz.CommentXyz], processor: CommentsProcessor):
    with ScopedSession() as session:   
        updated_comments = []
        prefetched_comment_id_pairs = []
        for comment in comments:
            if comment.id_xyz is not None and comment.id_ru is not None:
                comment_db = session.query(Comment).filter(Comment.comment_id == comment.id_ru).first()
                if comment_db is None or comment_db.comment_id_storage is None:
                    id_storage = session.query(CommentIdStorage).filter(CommentIdStorage.comment_id_ru == comment.id_ru).first()
                    if id_storage is None:
                        id_storage = CommentIdStorage()
                        id_storage.comment_id_ru = comment.id_ru
                        id_storage.comment_id_xyz = comment.id_xyz
                        session.add(id_storage)
                        prefetched_comment_id_pairs.append((comment.id_ru, comment.id_xyz))
                    elif id_storage.comment_id_xyz != comment.id_xyz:
                        id_storage.comment_id_xyz = comment.id_xyz
                        prefetched_comment_id_pairs.append((comment.id_ru, comment.id_xyz))

                    if comment_db is not None:
                        comment_db.comment_id_storage = id_storage
                        updated_comments.append(comment_db)

                elif comment_db.comment_id_storage.comment_id_xyz != comment.id_xyz:
                    comment_db.comment_id_storage.comment_id_xyz = comment.id_xyz
                    session.merge(comment_db.comment_id_storage)
                    updated_comments.append(comment_db)

        if len(prefetched_comment_id_pairs) > 0:
            session.flush()
            to_print: list = prefetched_comment_id_pairs[:5]
            if len(prefetched_comment_id_pairs) > 5:
                to_print.append('...')
            logging.info(f'Prefetched xyz ids for {len(prefetched_comment_id_pairs)} comments: [{", ".join(map(str, to_print))}]')

        if len(updated_comments) > 0:
            session.commit()
            to_print = [(c.comment_id, c.comment_id_storage.comment_id_xyz) for c in updated_comments[:5]]
            if len(updated_comments) > 5:
                to_print.append('...')
            logging.info(f'Fetched xyz ids for {len(updated_comments)} comments: [{", ".join(map(str, to_print))}]')
            processor.on_comments_update([], updated_comments)


def worker_ru(thread_exited_event: threading.Event):
    thread_exited_event.clear()
    processor = CommentsProcessor(config.REDIS_HOST,
                                  config.REDIS_PORT,
                                  config.REDIS_PASSWORD,
                                  config.REDIS_CHANNEL)
    logging.info("=== ru worker started ===")
    fast_requests = 0
    while True:
        try:
            comments = fetch_latest_comments()
            has_updates = update_sync_states(comments, processor)
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

        if exit_event.wait(delay):
            break
        
    thread_exited_event.set()


def worker_xyz(thread_exited_event: threading.Event):
    thread_exited_event.clear()
    processor = CommentsProcessor(config.REDIS_HOST,
                                  config.REDIS_PORT,
                                  config.REDIS_PASSWORD,
                                  config.REDIS_CHANNEL)
    logging.info("=== xyz worker started ===")
    fast_requests = 0
    last_xyz_id = -1
    while True:
        try:
            comments = fetch_latest_comments_xyz()
            update_xyz_states(comments, processor)

            if comments[0].id_xyz != last_xyz_id:
                fast_requests = FAST_TO_SLOW_STEPS
                last_xyz_id = comments[0].id_xyz
        except Exception as e:
            logging.exception(e)
            fast_requests = 0

        if fast_requests > 0:
            delay = FAST_DELAY
            fast_requests -= 1
        else:
            delay = SLOW_DELAY

        if exit_event.wait(delay):
            break

    thread_exited_event.set()


def graceful_exit(signum, frames):
    logging.info('Exiting...')
    exit_event.set()
    while not all((e.is_set() for e in threads_exited_events)):
        for e in threads_exited_events:
            e.wait()
    logging.info('All threads stopped. Goodbye!')


def main():
    threads_exited_events.append(threading.Event())
    thread_ru = threading.Thread(target=worker_ru, name='RU', args=(threads_exited_events[-1],))

    threads_exited_events.append(threading.Event())
    thread_xyz = threading.Thread(target=worker_xyz, name='RU', args=(threads_exited_events[-1],))

    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    thread_ru.start()
    thread_xyz.start()

    thread_ru.join()
    thread_xyz.join()


if __name__ == '__main__':
    main()
