import atexit
import datetime
import logging
import re
import signal
import threading
import time
from typing import Any, List, Optional, Sequence, Tuple

import lxml
import lxml.etree
import requests

from ngk import config, parser_xyz
from ngk.comments_processor import CommentsProcessor
from ngk.log import get_logger, redirect_basic_logging
from ngk.html_util import inner_html_ru, normalize_text
from ngk.parse_error import ParseError
from ngk.parser import ParsedComment, ParsedPost, ParsedUser
from ngk.parser_ru import parse_sink, parse_post
from ngk.schema import Comment, CommentIdStorage, ScopedSession, SyncState


L = get_logger('scan_comments', logging.INFO)
redirect_basic_logging(L)

COMMENTS_URL = 'http://govnokod.ru/comments'
COMMENTS_URL_XYZ = 'https://govnokod.xyz/comments/'
FAST_DELAY = 15
SLOW_DELAY = 60
FAST_TO_SLOW_STEPS = 20

GK_GUEST8_ID = 25580

exit_event = threading.Event()
threads_exited_events: List[threading.Event] = []


def fetch_latest_comments() -> List[ParsedComment]:
    L.debug("Fetching comments from ru...")
    r = requests.get(COMMENTS_URL, headers=config.DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    return parse_sink(r.content)


def fetch_latest_comments_xyz() -> List[parser_xyz.CommentXyz]:
    L.debug("Fetching comments from xyz...")
    r = requests.get(COMMENTS_URL_XYZ, headers=config.DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    root = lxml.etree.HTML(r.content)
    return parser_xyz.parse_comments(root)


def update_sync_states(comments: Sequence[ParsedComment], processor: CommentsProcessor) -> bool:
    has_updates = False
    updated_comments: List[Comment] = []
    with ScopedSession() as session:
        for comment_sink in comments:
            post_id, comment_id, comment_text = comment_sink.post_id, comment_sink.id_ru, comment_sink.text
            comment_db = session.query(Comment).filter(Comment.comment_id == comment_id).first()
            if comment_db is not None and comment_db.text != comment_text:
                comment_db.text = comment_text
                updated_comments.append(comment_db)

            state = session.query(SyncState).filter(SyncState.post_id == post_id).one_or_none()
            if not state:
                L.info("Got new comment %d for new post %d", comment_id, post_id)
                has_updates = True
                state = SyncState(post_id=post_id, last_comment_id=comment_id, pending=True, priority=SyncState.PRIORITY_HAS_COMMENTS)
                session.add(state)
            else:
                if state.last_comment_id is None or comment_id > state.last_comment_id:
                    L.info("Got new comment %d for post %d", comment_id, post_id)
                    has_updates = True
                    state.last_comment_id = comment_id
                    state.pending = True
                    state.priority=SyncState.PRIORITY_HAS_COMMENTS

        if len(updated_comments) > 0:
            L.info(f'Fast-fetched {len(updated_comments)} updated ' + \
                   f'comment{"s" if len(updated_comments) > 1 else ""}: {[c.comment_id for c in updated_comments]}')
            session.commit()
            processor.on_comments_update([], updated_comments)

    return has_updates


def update_xyz_states(comments: Sequence[parser_xyz.CommentXyz], processor: CommentsProcessor) -> None:
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
            L.info(f'Prefetched xyz ids for {len(prefetched_comment_id_pairs)} comments: [{", ".join(map(str, to_print))}]')

        if len(updated_comments) > 0:
            session.commit()
            to_print = [(c.comment_id, c.comment_id_storage.comment_id_xyz) for c in updated_comments[:5]]
            if len(updated_comments) > 5:
                to_print.append('...')
            L.info(f'Fetched xyz ids for {len(updated_comments)} comments: [{", ".join(map(str, to_print))}]')
            processor.on_comments_update([], updated_comments)


def worker_ru(thread_exited_event: threading.Event) -> None:
    thread_exited_event.clear()
    processor = CommentsProcessor(config.REDIS_HOST,
                                  config.REDIS_PORT,
                                  config.REDIS_PASSWORD,
                                  config.REDIS_CHANNEL,
                                  L)
    L.info("=== ru worker started ===")
    fast_requests = 0
    while True:
        try:
            comments = fetch_latest_comments()
            has_updates = update_sync_states(comments, processor)
            if has_updates:
                fast_requests = FAST_TO_SLOW_STEPS
        except Exception as e:
            L.exception(e)
            fast_requests = 0

        if fast_requests > 0:
            delay = FAST_DELAY
            fast_requests -= 1
        else:
            delay = SLOW_DELAY

        if exit_event.wait(delay):
            break
        
    thread_exited_event.set()


def worker_xyz(thread_exited_event: threading.Event) -> None:
    thread_exited_event.clear()
    processor = CommentsProcessor(config.REDIS_HOST,
                                  config.REDIS_PORT,
                                  config.REDIS_PASSWORD,
                                  config.REDIS_CHANNEL,
                                  L)
    L.info("=== xyz worker started ===")
    fast_requests = 0
    last_xyz_id: Optional[int] = -1
    while True:
        try:
            comments = fetch_latest_comments_xyz()
            update_xyz_states(comments, processor)

            if comments[0].id_xyz != last_xyz_id:
                fast_requests = FAST_TO_SLOW_STEPS
                last_xyz_id = comments[0].id_xyz
        except Exception as e:
            L.exception(e)
            fast_requests = 0

        if fast_requests > 0:
            delay = FAST_DELAY
            fast_requests -= 1
        else:
            delay = SLOW_DELAY

        if exit_event.wait(delay):
            break

    thread_exited_event.set()


def graceful_exit(signum: int, frames: Any) -> None:
    L.info('Exiting...')
    exit_event.set()
    while not all((e.is_set() for e in threads_exited_events)):
        for e in threads_exited_events:
            e.wait()
    L.info('All threads stopped. Goodbye!')


def main() -> None:
    threads_exited_events.append(threading.Event())
    thread_ru = threading.Thread(target=worker_ru, name='RU', args=(threads_exited_events[-1],))

    threads_exited_events.append(threading.Event())
    thread_xyz = threading.Thread(target=worker_xyz, name='XYZ', args=(threads_exited_events[-1],))

    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    thread_ru.start()
    thread_xyz.start()

    thread_ru.join()
    thread_xyz.join()


if __name__ == '__main__':
    main()
