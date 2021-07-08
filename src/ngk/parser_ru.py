import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple

import lxml.etree

from ngk.html_util import inner_html_ru, normalize_text
from ngk.parser import ParsedComment, ParsedPost, ParsedUser, ParseError


def _parse_date(date: str) -> datetime:
    date = re.sub(r'(\d\d):(\d\d)$', r'\1\2', date)
    return datetime.strptime(date, '%Y-%m-%dT%H:%M:%S%z').astimezone(timezone(timedelta()))


def _parse_avatar(url: str) -> Optional[str]:
    m = re.search(r'/avatar/([0-9a-f]{32})', url)
    if m:
        return m.group(1)
    else:
        return None


def _parse_comment_node(comment_wrapper: lxml.etree._Element, post_id: int, comment_id: int, parent_id: Optional[int] = None) -> ParsedComment:
    entry_comment_node = comment_wrapper.xpath('./div[contains(@class, "entry-comment")]')[0]  # sink (/comments)
    text_nodes = entry_comment_node.xpath('./span[@class="comment-text"]')          # normal post (/1234)
    if len(text_nodes) > 0:  
        entry_comment_node = text_nodes[0]

    text = normalize_text(inner_html_ru(entry_comment_node))

    info_node = comment_wrapper.xpath('./p[@class="entry-info"]')[0]
    time_posted = _parse_date(info_node.xpath('./abbr[@class="published"]')[0].get('title'))

    user_node = info_node.xpath('./strong[@class="entry-author"]/a')[0]
    m = re.search(r'/user/(\d+)$', user_node.get('href'))
    if m is None:
        raise ParseError('No comment\'s user id found')
    user_id = int(m.group(1))
    user_name = user_node.text
    user_avatar_hash = _parse_avatar(info_node.xpath('./img[@class="avatar"]')[0].get('src'))

    comment = ParsedComment(id_ru=comment_id,
                            id_xyz=None,
                            post_id=post_id,
                            parent_id=parent_id,
                            text=text,
                            user=ParsedUser(id_ru=user_id, id_xyz=None, name=user_name, avatar_hash=user_avatar_hash),
                            time_posted=time_posted.timestamp(),
                            time_parsed=time.time())
    return comment


# all_at_once = True for the sink parsing (/comments), False for optimized post parsing
def _parse_comments(comments_node: lxml.etree._Element, all_at_once: bool = False) -> List[ParsedComment]:
    comments: List[ParsedComment] = []

    if all_at_once:
        hcomment_xpath = './/li[@class="hcomment"]'
    else:
        hcomment_xpath = './li[@class="hcomment"]'
    
    comment_nodes: List[Tuple[Optional[int], Any]] = [(None, c) for c in comments_node.xpath(hcomment_xpath)]

    while len(comment_nodes) > 0:
        parent_id, comment_node = comment_nodes.pop()

        comment_wrapper = comment_node.xpath('./div[@class="entry-comment-wrapper"]')[0]
        comment_link = comment_wrapper.xpath('./p[@class="entry-info"]/a[@class="comment-link"]')[0]
        m = re.search(r'govnokod\.ru/(\d+)#comment(\d+)$', comment_link.get('href', ''))
        if m is None:
            raise ParseError('Invalid comment-link (no regex match)')
        post_id = int(m.group(1))
        comment_id = int(m.group(2))
        comments.append(_parse_comment_node(comment_wrapper, post_id, comment_id, parent_id))

        for node in comment_node.xpath('./ul/li[@class="hcomment"]'):
            comment_nodes.append((comment_id, node))

    return comments


def parse_sink(content: bytes) -> List[ParsedComment]:
    parser = lxml.etree.HTMLParser(recover=True, huge_tree=True)
    root = lxml.etree.HTML(content, parser=parser)
    return _parse_comments(root, all_at_once=True)


# ('id_ru', 'id_xyz', 'code', 'text', 'user', 'comments', 'time_posted', 'time_parsed')
# An extremely ugly hack to fix GK's incorrect
# <pre> usage within the <p> tag
_RE_DESCRIPTION_TAG_OPEN = re.compile(r'<p\s+class="description">'.encode('utf-8'))
_RE_DESCRIPTION_TAG_CLOSE = re.compile(r'</p>\s*<p\s+class="author">'.encode('utf-8'))
def _fix_ru_description_tag(content: bytes, new_tag: str) -> bytes:
    content = _RE_DESCRIPTION_TAG_OPEN .sub(f'<{new_tag} class="description">'.encode('utf-8'), content)
    return    _RE_DESCRIPTION_TAG_CLOSE.sub(f'</{new_tag}><p class="author">'.encode('utf-8'), content)


def parse_post(content: bytes) -> ParsedPost:
    content = _fix_ru_description_tag(content, 'div')

    # Note: this code needs (patched | recent) lxml with support for huge_tree in HTMLParser
    parser = lxml.etree.HTMLParser(recover=True, huge_tree=True)
    root = lxml.etree.HTML(content, parser=parser)

    try:
        post_node = root.xpath('//li[@class="hentry"]')[0]
        author_node = post_node.xpath('.//p[@class="author"]')[0]
        comments_node = post_node.xpath('./div[@class="entry-comments"]/ul')[0]
    except IndexError:
        raise ParseError('Invalid document (no post_node/author_node/comments_node)')

    # author info
    user_url = author_node.xpath('a[1]')[0].get('href')
    m = re.search(r'/user/(\d+)$', user_url)
    if m is None:
        raise ParseError('No post\'s user id found')
    user_id = int(m.group(1))
    user_name = author_node.xpath('./a[contains(@href, "/user/") and text()]')[0].text
    try:
        user_avatar_hash = _parse_avatar(author_node.xpath('./a/img[@class="avatar"]')[0].get('src'))
    except IndexError:  # Old posts by guest
        user_avatar_hash = None
    user = ParsedUser(id_ru=user_id, id_xyz=None, name=user_name, avatar_hash=user_avatar_hash)

    # post
    post_url = post_node.xpath('.//a[@class="entry-title"]')[0].get('href')
    m = re.search(r'/(\d+)$', post_url)
    if m is None:
        raise ParseError('Post id not found')
    post_id = int(m.group(1))

    comment_list_raw = comments_node.get("id")
    m = re.match(r'comments_(\d+)$', comment_list_raw)
    if m is None:
        raise ParseError('Comments_list_id not found')
    comment_list_id = int(m.group(1))

    language = post_node.xpath('.//a[@rel="chapter"]')[0].text

    post_content = post_node.xpath('div[@class="entry-content"]')[0]
    post_code_nodes = post_content.xpath('.//code')
    if len(post_code_nodes) > 0:
        code = post_code_nodes[0].text
    else:
        code = inner_html_ru(post_content)
    
    text = normalize_text(inner_html_ru(post_node.xpath('div[@class="description"]')[0]))

    try:
        posted = _parse_date(author_node.xpath('./abbr')[0].get('title'))
    except IndexError:
        raise ParseError('Post date not found (old html?)')

    comments = _parse_comments(comments_node, all_at_once=False)

    # ('id_ru', 'id_xyz', 'comment_list_id', 'language', 'code', 'text', 'user', 'comments', 'time_posted', 'time_parsed')
    post = ParsedPost(
        id_ru=post_id,
        id_xyz=None,
        comment_list_id=comment_list_id,
        language=language,
        code=code,
        text=text,
        user=user,
        comments=comments,
        time_posted=posted.timestamp(),
        time_parsed=time.time()
    )
    return post
