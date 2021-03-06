import copy
import datetime
import math
import re
import time
import timeit
from typing import Any, Dict, Mapping, Union, List, Optional

import lxml
import lxml.etree
import lxml.html
import lxml.sax

from ngk.html_util import inner_html_xyz, normalize_text
from ngk.parse_error import ParseError
from ngk.schema import DATE_FORMAT


_COMMENT_LINK_XYZ_RE = re.compile(r'^https?://govnokod.xyz/_(\d+)/#comment-(\d+)/?$')
_COMMENT_LINK_RU_RE = re.compile(r'^https?://govnokod.ru/(\d+)#comment(\d+)/?$')
_USER_LINK_XYZ_RE = re.compile(r'^https?://govnokod.xyz/user/(\d+)/?$')
_USER_LINK_RU_RE = re.compile(r'^https?://govnokod.ru/user/(\d+)/?$')


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
    
    def to_dict(self) -> Dict[str, Union[int, str, float, None]]:
        return {k: getattr(self, k) for k in CommentXyz.__slots__}
    
    @staticmethod
    def from_dict(dictionary: Mapping[str, Union[int, str, float, None]]) -> 'CommentXyz':
        slots_set = set(CommentXyz.__slots__)
        dict_set = set(dictionary.keys())

        required_keys = slots_set.difference(dict_set)
        if len(required_keys) > 0:
            raise TypeError(f'Not enough keys: {required_keys} required')

        unexpected_keys = dict_set.difference(slots_set.intersection(dict_set))
        if len(unexpected_keys) > 0:
            raise TypeError(f'Unexpected keys present: {unexpected_keys}')

        return CommentXyz(**dictionary)  # type: ignore

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, CommentXyz):
            attrs = set(CommentXyz.__slots__)
            attrs.remove('time_posted')
            attrs.remove('time_parsed')
            return all((
                math.isclose(self.time_posted, other.time_posted),
                math.isclose(self.time_parsed, other.time_parsed),
                all((getattr(self, attr) == getattr(other, attr) for attr in attrs))
            ))
        else:
            return False

    def __str__(self) -> str:
        time_posted = datetime.datetime.fromtimestamp(self.time_posted).strftime(DATE_FORMAT)
        time_parsed = datetime.datetime.fromtimestamp(self.time_parsed).strftime(DATE_FORMAT)
        return f'XYZ Comment {self.id_ru}/{self.id_xyz}, user_id_ru {self.user_id_ru}, ' + \
               f'user_id_xyz {self.user_id_xyz}, post_id {self.post_id}, posted {time_posted}, parsed {time_parsed}'

    def __repr__(self) -> str:
        return f'CommentXyz({self.id_ru}, {self.id_xyz}, {self.post_id},' + \
               f'{self.text}, {self.user_id_ru}, {self.user_id_xyz}, {self.time_posted}, {self.time_parsed})'


def parse_comments(root: lxml.etree._Element) -> List[CommentXyz]:
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

        comment_link_nodes = info_node.xpath('a[@class="comment-link"]')
        if len(comment_link_nodes) == 0:
            raise ParseError('No comment-link node found')
        comment_link = comment_link_nodes[0]
        
        href = comment_link.get('href', None)
        if href is None:
            raise ParseError('No href attribute in the comment-link node found')

        id_ru_attr = comment_link.get('data-legacy-id', None)
        if id_ru_attr is not None and len(id_ru_attr) > 0:
            id_ru = int(id_ru_attr)
        
        for link_node in info_node.xpath('.//a'):
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
