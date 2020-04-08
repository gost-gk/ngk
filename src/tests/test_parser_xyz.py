import math
import json
import os
import pathlib
from typing import Union

import lxml
import lxml.etree
import lxml.html

from ngk.parser_xyz import CommentXyz, parse_comments


class Test_CommentXyz:
    def test_eq(self) -> None:
        comment  = CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7)
        comments = [
            CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=0, id_xyz=2, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=0, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=2, post_id=0, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='olleH', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='Hello', user_id_ru=0, user_id_xyz=5, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=0, time_posted=1/3, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3 - 0.00001, time_parsed=1/7),
            CommentXyz(id_ru=1, id_xyz=2, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=5, time_posted=1/3, time_parsed=1/7 + 0.00001)
        ]

        assert comment == comments[0]
        for comment_not_eq in comments[1:]:
            assert comment != comment_not_eq
    
    def test_to_dict(self) -> None:
        attrs = {
            'id_ru': 1,
            'id_xyz': None,
            'post_id': 3,
            'text': 'Hello',
            'user_id_ru': 4,
            'user_id_xyz': None,
            'time_posted': 16,
            'time_parsed': 256
        }
        
        comment = CommentXyz(id_ru=1, id_xyz=None, post_id=3, text='Hello', user_id_ru=4, user_id_xyz=None, time_posted=16, time_parsed=256)
        attrs_comment = comment.to_dict()

        assert attrs_comment == attrs
            
    def test_from_dict(self) -> None:
        attrs = {
            'id_ru': 1,
            'id_xyz': None,
            'post_id': 3,
            'text': 'Hello',
            'user_id_ru': 4,
            'user_id_xyz': None,
            'time_posted': 16,
            'time_parsed': 256
        }

        comment = CommentXyz.from_dict(attrs)
        for attr in attrs:
            assert getattr(comment, attr) == attrs[attr]


class Test_parse_comments:
    def _test_on_files(self, path_html: Union[str, pathlib.Path], path_json: Union[str, pathlib.Path]) -> None:
        with open(path_html, 'rb') as f_html:
            html_bytes = f_html.read()
        with open(path_json, 'r', encoding='utf-8') as f_json:
            comments_real = [CommentXyz.from_dict(c) for c in json.loads(f_json.read())]

        root = lxml.etree.HTML(html_bytes)
        comments_parsed = parse_comments(root)

        assert len(comments_parsed) == len(comments_real)

        for comment_parsed, comment_real in zip(comments_parsed, comments_real):
            comment_parsed.time_parsed = comment_real.time_parsed
            assert comment_parsed == comment_real

    def test_real_comments(self) -> None:
        data_dir = pathlib.Path(os.path.dirname(os.path.realpath(__file__))).joinpath('data')
        self._test_on_files(data_dir.joinpath('xyz_comments.html'), data_dir.joinpath('xyz_comments.json'))

    def test_real_post(self) -> None:
        data_dir = pathlib.Path(os.path.dirname(os.path.realpath(__file__))).joinpath('data')
        self._test_on_files(data_dir.joinpath('xyz_post.html'), data_dir.joinpath('xyz_post.json'))
