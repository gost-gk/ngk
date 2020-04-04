import copy
import datetime
import logging
import re
import time
import timeit
from typing import List, Optional

import lxml
import lxml.etree
import lxml.html
import lxml.sax
import requests

from html_util import inner_html_xyz, normalize_text
from schema import Comment, DATE_FORMAT, ScopedSession


_COMMENT_LINK_XYZ_RE = re.compile(r'^https?://govnokod.xyz/_(\d+)/#comment-(\d+)/?$')
_COMMENT_LINK_RU_RE = re.compile(r'^https?://govnokod.ru/(\d+)#comment(\d+)/?$')
_USER_LINK_XYZ_RE = re.compile(r'^https?://govnokod.xyz/user/(\d+)/?$')
_USER_LINK_RU_RE = re.compile(r'^https?://govnokod.ru/user/(\d+)/?$')


class ParseError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CommentXyz:
    __slots__ = ('id_ru', 'id_xyz', 'post_id', 'text', 'user_id_ru', 'user_id_xyz', 'time_posted', 'time_parsed')
    
    def __init__(self,
                 id_ru: Optional[int],
                 id_xyz: Optional[int],
                 post_id: int,
                 text: str,
                 user_id_ru: Optional[int],
                 user_id_xyz: Optional[int],
                 time_posted: float,
                 time_parsed: float):
        self.id_ru: Optional[int] = id_ru
        self.id_xyz: Optional[int] = id_xyz
        self.post_id: int = post_id
        self.text: str = text
        self.user_id_ru: Optional[int] = user_id_ru
        self.user_id_xyz: Optional[int] = user_id_xyz
        self.time_posted: float = time_posted
        self.time_parsed: float = time_parsed
    
    def __str__(self):
        time_posted = datetime.datetime.fromtimestamp(self.time_posted).strftime(DATE_FORMAT)
        time_parsed = datetime.datetime.fromtimestamp(self.time_parsed).strftime(DATE_FORMAT)
        return f'Update comment {self.id_ru}/{self.id_xyz}, user_id_ru {self.user_id_ru}, ' + \
               f'user_id_xyz {self.user_id_xyz}, post_id {self.post_id}, posted {time_posted}, parsed {time_parsed}'

    def __repr__(self):
        return f'CommentUpdate({self.id_ru}, {self.id_xyz}, {self.post_id},' + \
               f'{self.text}, {self.user_id_ru}, {self.user_id_xyz}, {self.time_posted}, {self.time_parsed})'


def parse_comments(root) -> List[CommentXyz]:
    comments: List[CommentXyz] = []

    comment_entry_nodes = root.xpath('//li[@class="hcomment"]')
    if len(comment_entry_nodes) == 0:
        comment_entry_nodes = root.xpath('//article[starts-with(@id, "div-comment")]')
    if len(comment_entry_nodes) == 0:
        raise ParseError('No comment entries found')

    for comment_entry in comment_entry_nodes:
        info_nodes = comment_entry.xpath('.//p[@class="entry-info" or @class="comment-meta entry-info"]')
        if len(info_nodes) == 0:
            raise ParseError('No entry-info node found')
        info_node = info_nodes[0]
        
        comment_nodes = comment_entry.xpath('.//div[@class="comment-content entry-comment" or @class="entry-comment"]')
        if len(comment_nodes) == 0:
            raise ParseError('No entry-comment node found')
        comment_node = comment_nodes[0]
            
        id_ru = None
        id_xyz = None
        user_id_ru = None
        user_id_xyz = None
        post_id = None
        comment_text = normalize_text(inner_html_xyz(comment_node))

        for link_node in info_node.xpath('a'):
            link = link_node.get('href', '')

            match = _COMMENT_LINK_XYZ_RE.match(link)
            if match is not None:
                post_id = int(match.group(1))
                id_xyz = int(match.group(2))
            
            match = _COMMENT_LINK_RU_RE.match(link)
            if match is not None:
                post_id = int(match.group(1))
                id_ru = int(match.group(2))

            match = _USER_LINK_XYZ_RE.match(link)
            if match is not None:
                user_id_xyz = int(match.group(1))

            match = _USER_LINK_RU_RE.match(link)
            if match is not None:
                user_id_ru = int(match.group(1))

        try:
            time_node = info_node.xpath('.//time')[0]
        except IndexError:
            raise ParseError('No time element found')
            
        posted_time = time_node.get('datetime', None)

        if id_ru is None and id_xyz is None:
            raise ParseError('No comment_id found (both id_ru and id_xyz are None)')

        if post_id is None:
            raise ParseError(f'No post_id found ({id_ru}/{id_xyz})')

        if posted_time is None:
            raise ParseError('No posted_time found')

        time_parsed_timestamp = time.time()
        time_posted_timestamp = datetime.datetime.fromisoformat(posted_time).timestamp()
        comment = CommentXyz(id_ru, id_xyz, post_id, comment_text, user_id_ru, user_id_xyz, time_posted_timestamp, time_parsed_timestamp)
        comments.append(comment)

    return comments
