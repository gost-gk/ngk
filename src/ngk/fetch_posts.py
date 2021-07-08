from datetime import datetime, timedelta, timezone
import decimal
import logging
import os
import os.path
import re
import time
from typing import List, Optional, Tuple

import lxml
import lxml.etree
import lxml.html
import requests
import sqlalchemy.orm

from ngk.comments_processor import CommentsProcessor
from ngk import config
from ngk.log import get_logger, redirect_basic_logging
from ngk.html_util import inner_html_ru, normalize_text
from ngk.parse_error import ParseError
from ngk.parser import ParsedComment, ParsedPost, ParsedUser
import ngk.parser_ru as parser_ru
from ngk.schema import Comment, Post, ScopedSession, SyncState, User


L = get_logger('fetch_posts', logging.DEBUG)
redirect_basic_logging(L)

GK_URL = "http://govnokod.ru"
SUCCESS_DELAY = 5
ERROR_DELAY = 60

    
def parse_post(content: bytes) -> Tuple[Post, List[User], List[Comment]]:
    parsed_post: ParsedPost = parser_ru.parse_post(content)
    parsed_user: ParsedUser = parsed_post.user
    parsed_comments: List[ParsedComment] = parsed_post.comments
    
    users: List[User] = []
    comments: List[Comment] = []

    # post
    post = Post(
        source=Post.SOURCE_GK,
        post_id=parsed_post.id_ru,
        user_id=parsed_user.id_ru,
        comment_list_id=parsed_post.comment_list_id,
        language=parsed_post.language,
        code=parsed_post.code,
        text=parsed_post.text,
        posted=datetime.fromtimestamp(parsed_post.time_posted),
        vote_plus=0,
        vote_minus=0,
        rating=0
    )

    # author info
    user = User(
        source=User.SOURCE_GK,
        user_id=parsed_user.id_ru,
        name=parsed_user.name,
        avatar_hash=parsed_user.avatar_hash
    )
    users.append(user)

    # comments
    for parsed_comment in parsed_comments:
        user = User(
            source=User.SOURCE_GK,
            user_id=parsed_comment.user.id_ru,
            name=parsed_comment.user.name,
            avatar_hash=parsed_comment.user.avatar_hash
        )
        
        comment = Comment(parsed_comment.id_ru)
        comment.user_id = parsed_comment.user.id_ru
        comment.source = Comment.SOURCE_GK
        comment.post_id = parsed_post.id_ru
        comment.parent_id = parsed_comment.parent_id
        comment.text = parsed_comment.text
        comment.posted = datetime.fromtimestamp(parsed_comment.time_posted)
        comment.vote_plus = 0
        comment.vote_minus = 0
        comment.rating = 0

        users.append(user)
        comments.append(comment)

    return (post, users, comments)


def update_state(state: SyncState, result: str) -> None:
    L.info("Update result: %s", result)
    state.pending = False
    state.synced = datetime.utcnow()
    state.result = result


def dump_post(content: bytes) -> None:
    time = datetime.utcnow()
    subdir_path = config.get_dumps_path(time.strftime("%Y-%m-%d"))
    file_name = time.strftime("%H-%M-%S") + ".html"
    if not os.path.isdir(subdir_path):
        os.makedirs(subdir_path)
    with open(os.path.join(subdir_path, file_name), 'wb') as f:
        f.write(content)


def update_post(session: sqlalchemy.orm.Session, state: SyncState, processor: CommentsProcessor) -> None:
    L.info("Updating post %d...", state.post_id)

    r = requests.get(GK_URL + "/" + str(state.post_id), headers=config.DEFAULT_HEADERS, timeout=30)
    if r.status_code != 200:
        update_state(state, 'HTTP error {0}'.format(r.status_code))
        return

    dump_post(r.content)

    try:
        post, users, comments = parse_post(r.content)
    except Exception as e:
        L.exception(e)
        update_state(state, 'Parse error')
        return

    session.merge(post)
    for user in users:
        session.merge(user)

    last_comment_id = None
    updated_comments: List[Comment] = []
    new_comments: List[Comment] = []

    for comment in comments:
        old_text = session.query(Comment.text).filter(Comment.comment_id == comment.comment_id).first()
        merged_comment = session.merge(comment)
        if old_text is None:
            new_comments.append(merged_comment)
        elif old_text[0] != merged_comment.text:
            updated_comments.append(merged_comment)
        if last_comment_id is None or comment.comment_id > last_comment_id:
            last_comment_id = comment.comment_id

    update_state(state, 'OK')
    session.flush()
    processor.on_comments_update(new_comments, updated_comments)
    
    # Workaround for https://govnokod.ru/26440#comment527494
    # TODO: Make an appropriate fix
    session.commit()
    if last_comment_id is not None:
        if state.last_comment_id is not None and state.last_comment_id > last_comment_id:
            # scan_comments.py changed state while we were parsing the post
            L.warning(f'state.last_comment_id changed during post {post.post_id} ' \
                    + f'parsing: {state.last_comment_id} > {last_comment_id}')
            state.pending = True 
            session.flush()
    state.last_comment_id = last_comment_id


def update_next_post(processor: CommentsProcessor) -> None:
    try:
        with ScopedSession() as session:
            state = session.query(SyncState).filter_by(pending=True).order_by(SyncState.priority.desc(), SyncState.post_id.desc()).first()
            if state:
                update_post(session, state, processor)

        delay = SUCCESS_DELAY

    except Exception as e:
        L.exception(e)
        delay = ERROR_DELAY

    time.sleep(delay)


def main() -> None:
    L.info("=== started ===")
    processor = CommentsProcessor(config.REDIS_HOST,
                                  config.REDIS_PORT,
                                  config.REDIS_PASSWORD,
                                  config.REDIS_CHANNEL,
                                  L)
    while True:
        update_next_post(processor)


if __name__ == '__main__':
    main()
