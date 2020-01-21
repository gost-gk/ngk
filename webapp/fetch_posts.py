from datetime import datetime, timedelta, timezone
import decimal
import logging
import os
import os.path
import re
import time

import lxml
import lxml.etree
import lxml.html
import requests
from decouple import config

from comments_processor import CommentsProcessor
from schema import Comment, Post, ScopedSession, SyncState, User


logging.basicConfig(
    filename="../logs/fetch_posts.log",
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG)


GK_URL = "http://govnokod.ru"
SUCCESS_DELAY = 5
ERROR_DELAY = 60
DUMP_DIR = "../dumps"

def inner_html(node):
    tmp = lxml.etree.Element("root")
    tmp.text = node.text
    for child in node:
        tmp.append(child)

    res = lxml.html.tostring(tmp, encoding='unicode')
    return re.sub(r'</root>$', '', re.sub(r'^<root>', '', res)).strip()

def parse_date(date):
    date = re.sub(r'(\d\d):(\d\d)$', r'\1\2', date)
    return datetime.strptime(date, '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone(timedelta()))

def parse_avatar(url):
    m = re.search(r'/avatar/([0-9a-f]{32})', url)
    if m:
        return m.group(1)
    else:
        return None

def parse_rating(rating_node):
    m = re.match(r'(\d+) .* (\d+) .*$', rating_node.get('title'))
    plus = int(m.group(1))
    minus = int(m.group(2))
    rating = decimal.Decimal(rating_node.text.replace('−', '-'))
    return plus, minus, rating


# An extremely ugly hack to fix GK's incorrect
# <pre> usage within the <p> tag
_RE_DESCRIPTION_TAG_OPEN = re.compile(r'<p\s+class="description">'.encode('utf-8'))
_RE_DESCRIPTION_TAG_CLOSE = re.compile(r'</p>\s*<p\s+class="author">'.encode('utf-8'))
def replace_description_tag(content, new_tag):
    content = _RE_DESCRIPTION_TAG_OPEN .sub(f'<{new_tag} class="description">'.encode('utf-8'), content)
    return    _RE_DESCRIPTION_TAG_CLOSE.sub(f'</{new_tag}><p class="author">'.encode('utf-8'), content)
    
    
def parse_post(content):
    content = replace_description_tag(content, 'div')
    post = Post()
    users = []
    comments = []

    # Note: this code needs patched lxml with support for huge_tree in HTMLParser
    parser = lxml.etree.HTMLParser(recover=True, huge_tree=True)
    root = lxml.etree.HTML(content, parser=parser)

    # post
    post_node = root.xpath('//li[@class="hentry"]')[0]
    comments_node = post_node.xpath('.//div[@class="entry-comments"]')[0]
    author_node = post_node.xpath('.//p[@class="author"]')[0]

    post_url = post_node.xpath('.//a[@class="entry-title"]')[0].get('href')
    post.source = Post.SOURCE_GK
    post.post_id = int(re.search(r'/(\d+)$', post_url).group(1))

    comment_list_raw = comments_node.xpath('ul')[0].get("id")
    post.comment_list_id = int(re.match(r'comments_(\d+)$', comment_list_raw).group(1))

    post.language = post_node.xpath('.//a[@rel="chapter"]')[0].text

    post.code = post_node.xpath('div[@class="entry-content"]/pre/code')[0].text
    post.text = inner_html(post_node.xpath('div[@class="description"]')[0])

    post.posted = parse_date(author_node.xpath('abbr')[0].get('title'))

    post.vote_plus, post.vote_minus, post.rating = parse_rating(post_node.xpath('p[@class="vote"]/strong')[0])

    # author info
    user = User()

    user_url = author_node.xpath('a[1]')[0].get('href')
    user.source = User.SOURCE_GK
    user.user_id = int(re.search(r'/user/(\d+)$', user_url).group(1))
    user.name = author_node.xpath('a[2]')[0].text
    user.avatar_hash = parse_avatar(author_node.xpath('a[1]/img')[0].get('src'))

    post.user_id = user.user_id
    users.append(user)

    # comments
    for comment_node in comments_node.xpath('.//div[@class="entry-comment-wrapper"]'):
        comment = Comment()

        comment.source = Comment.SOURCE_GK
        comment.comment_id = int(re.match(r'comment-(\d+)$', comment_node.get('id')).group(1))
        comment.post_id = post.post_id

        parent_node = comment_node.getparent().getparent().getparent()
        if parent_node.tag == 'li':
            parent_node = parent_node.xpath('div[@class="entry-comment-wrapper"]')[0]
            comment.parent_id = int(re.match(r'comment-(\d+)$', parent_node.get('id')).group(1))
        else:
            comment.parent_id = None

        comment.text = inner_html(comment_node.xpath('.//span[@class="comment-text"]')[0])

        info_node = comment_node.xpath('p[@class="entry-info"]')[0]

        comment.posted = parse_date(info_node.xpath('abbr[@class="published"]')[0].get('title'))
        comment.vote_plus, comment.vote_minus, comment.rating = parse_rating(info_node.xpath('span[@class="comment-vote"]/strong')[0])

        user_node = info_node.xpath('strong[@class="entry-author"]/a')[0]

        user = User()
        user.user_id = int(re.search(r'/user/(\d+)$', user_node.get('href')).group(1))
        user.name = user_node.text
        user.avatar_hash = parse_avatar(info_node.xpath('img[@class="avatar"]')[0].get('src'))

        comment.user_id = user.user_id
        users.append(user)
        comments.append(comment)

    return (post, users, comments)

def update_state(state, result):
    logging.info("Update result: %s", result)
    state.pending = False
    state.synced = datetime.utcnow()
    state.result = result

def dump_post(content):
    time = datetime.utcnow()
    subdir_path = os.path.join(DUMP_DIR, time.strftime("%Y-%m-%d"))
    file_name = time.strftime("%H-%M-%S") + ".html"
    if not os.path.isdir(subdir_path):
        os.makedirs(subdir_path)
    with open(os.path.join(subdir_path, file_name), 'wb') as f:
        f.write(content)

def update_post(session, state, processor: CommentsProcessor):
    logging.info("Updating post %d...", state.post_id)

    r = requests.get(GK_URL + "/" + str(state.post_id), timeout=30)
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
    for comment in comments:
        session.merge(comment)
        if last_comment_id is None or comment.comment_id > last_comment_id:
            last_comment_id = comment.comment_id

    state.last_comment_id = last_comment_id
    update_state(state, 'OK')
    processor.on_post_updated(post, users, comments)


def update_next_post(processor: CommentsProcessor):
    try:
        with ScopedSession() as session:
            state = session.query(SyncState).filter_by(pending=True).order_by(SyncState.priority, SyncState.post_id.desc()).first()
            if state:
                update_post(session, state, processor)

        delay = SUCCESS_DELAY

    except Exception as e:
        logging.exception(e)
        delay = ERROR_DELAY

    time.sleep(delay)


def main():
    logging.info("=== started ===")
    processor = CommentsProcessor(config('REDIS_HOST'),
                                  config('REDIS_PORT'),
                                  config('REDIS_PASSWORD'),
                                  config('REDIS_CHANNEL'))
    while True:
        update_next_post(processor)


if __name__ == '__main__':
    main()
