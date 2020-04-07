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
from ngk.html_util import inner_html_ru, normalize_text
from ngk.parse_error import ParseError
from ngk.schema import Comment, Post, ScopedSession, SyncState, User


GK_URL = "http://govnokod.ru"
SUCCESS_DELAY = 5
ERROR_DELAY = 60


root_logger= logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(config.get_log_path('fetch_posts.log'), 'w', 'utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S'))
root_logger.addHandler(handler)


def parse_date(date: str) -> datetime:
    date = re.sub(r'(\d\d):(\d\d)$', r'\1\2', date)
    return datetime.strptime(date, '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone(timedelta()))


def parse_avatar(url: str) -> Optional[str]:
    m = re.search(r'/avatar/([0-9a-f]{32})', url)
    if m:
        return m.group(1)
    else:
        return None


def parse_rating(rating_node: lxml.etree._Element) -> Tuple[int, int, decimal.Decimal]:
    title: str = rating_node.get('title', '')
    m = re.match(r'(\d+) .* (\d+) .*$', title)
    if m is None:
        _MAX_PRINT_LEN = 100
        logging.warning(f'Could not parse rating: no regex match in' +\
                        f'"{title[:_MAX_PRINT_LEN]}{"..." if len(title) > _MAX_PRINT_LEN else ""}"')
        return (0, 0, decimal.Decimal(0))
    plus = int(m.group(1))
    minus = int(m.group(2))
    rating = decimal.Decimal(rating_node.text.replace('−', '-'))
    return plus, minus, rating


# An extremely ugly hack to fix GK's incorrect
# <pre> usage within the <p> tag
_RE_DESCRIPTION_TAG_OPEN = re.compile(r'<p\s+class="description">'.encode('utf-8'))
_RE_DESCRIPTION_TAG_CLOSE = re.compile(r'</p>\s*<p\s+class="author">'.encode('utf-8'))
def replace_description_tag(content: bytes, new_tag: str) -> bytes:
    content = _RE_DESCRIPTION_TAG_OPEN .sub(f'<{new_tag} class="description">'.encode('utf-8'), content)
    return    _RE_DESCRIPTION_TAG_CLOSE.sub(f'</{new_tag}><p class="author">'.encode('utf-8'), content)
    
    
def parse_post(content: bytes) -> Tuple[Post, List[User], List[Comment]]:
    content = replace_description_tag(content, 'div')
    post = Post()
    users: List[User] = []
    comments: List[Comment] = []

    # Note: this code needs patched lxml with support for huge_tree in HTMLParser
    parser = lxml.etree.HTMLParser(recover=True, huge_tree=True)
    root = lxml.etree.HTML(content, parser=parser)

    # post
    post_node = root.xpath('//li[@class="hentry"]')[0]
    comments_node = post_node.xpath('.//div[@class="entry-comments"]')[0]
    author_node = post_node.xpath('.//p[@class="author"]')[0]

    post_url = post_node.xpath('.//a[@class="entry-title"]')[0].get('href')
    post.source = Post.SOURCE_GK
    m = re.search(r'/(\d+)$', post_url)
    if m is None:
        raise ParseError('Post id not found')
    post.post_id = int(m.group(1))

    comment_list_raw = comments_node.xpath('ul')[0].get("id")
    m = re.match(r'comments_(\d+)$', comment_list_raw)
    if m is None:
        raise ParseError('Comments_list_id not found')
    post.comment_list_id = int(m.group(1))

    post.language = post_node.xpath('.//a[@rel="chapter"]')[0].text

    post.code = post_node.xpath('div[@class="entry-content"]/pre/code')[0].text
    post.text = normalize_text(inner_html_ru(post_node.xpath('div[@class="description"]')[0]))

    post.posted = parse_date(author_node.xpath('abbr')[0].get('title'))

    post.vote_plus, post.vote_minus, post.rating = parse_rating(post_node.xpath('p[@class="vote"]/strong')[0])

    # author info
    user = User()

    user_url = author_node.xpath('a[1]')[0].get('href')
    user.source = User.SOURCE_GK
    m = re.search(r'/user/(\d+)$', user_url)
    if m is None:
        raise ParseError('No post\'s user id found')
    user.user_id = int(m.group(1))
    user.name = author_node.xpath('a[2]')[0].text
    user.avatar_hash = parse_avatar(author_node.xpath('a[1]/img')[0].get('src'))

    post.user_id = user.user_id
    users.append(user)

    # comments
    for comment_node in comments_node.xpath('.//div[@class="entry-comment-wrapper"]'):
        m = re.match(r'comment-(\d+)$', comment_node.get('id', ''))
        if m is None:
            raise ParseError('No comment id found')
        comment_id = int(m.group(1))

        comment = Comment(comment_id)
        comment.source = Comment.SOURCE_GK
        comment.post_id = post.post_id

        parent_node = comment_node.getparent().getparent().getparent()
        if parent_node.tag == 'li':
            parent_node = parent_node.xpath('div[@class="entry-comment-wrapper"]')[0]
            m = re.match(r'comment-(\d+)$', parent_node.get('id'))
            if m is None:
                raise ParseError('No parent comment id found')
            comment.parent_id = int(m.group(1))
        else:
            comment.parent_id = None

        comment.text = normalize_text(inner_html_ru(comment_node.xpath('.//span[@class="comment-text"]')[0]))

        info_node = comment_node.xpath('p[@class="entry-info"]')[0]

        comment.posted = parse_date(info_node.xpath('abbr[@class="published"]')[0].get('title'))
        comment.vote_plus, comment.vote_minus, comment.rating = parse_rating(info_node.xpath('span[@class="comment-vote"]/strong')[0])

        user_node = info_node.xpath('strong[@class="entry-author"]/a')[0]

        user = User()
        m = re.search(r'/user/(\d+)$', user_node.get('href'))
        if m is None:
            raise ParseError('No comment\'s user id found')
        user.user_id = int(m.group(1))
        user.name = user_node.text
        user.avatar_hash = parse_avatar(info_node.xpath('img[@class="avatar"]')[0].get('src'))

        comment.user_id = user.user_id
        users.append(user)
        comments.append(comment)

    return (post, users, comments)


def update_state(state: SyncState, result: str) -> None:
    logging.info("Update result: %s", result)
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
    logging.info("Updating post %d...", state.post_id)

    r = requests.get(GK_URL + "/" + str(state.post_id), headers=config.DEFAULT_HEADERS, timeout=30)
    if r.status_code != 200:
        update_state(state, 'HTTP error {0}'.format(r.status_code))
        return

    dump_post(r.content)

    try:
        post, users, comments = parse_post(r.content)
    except Exception as e:
        logging.exception(e)
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
            logging.warning(f'state.last_comment_id changed during post {post.post_id} '
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
        logging.exception(e)
        delay = ERROR_DELAY

    time.sleep(delay)


def main() -> None:
    logging.info("=== started ===")
    processor = CommentsProcessor(config.REDIS_HOST,
                                  config.REDIS_PORT,
                                  config.REDIS_PASSWORD,
                                  config.REDIS_CHANNEL)
    while True:
        update_next_post(processor)


if __name__ == '__main__':
    main()