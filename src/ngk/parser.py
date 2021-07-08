import dataclasses
import datetime
import math
from typing import Any, Dict, List, Mapping, Optional, Union

from ngk.schema import DATE_FORMAT, User, Comment, Post


class ParseError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


@dataclasses.dataclass
class ParsedUser:
    __slots__ = ('name', 'avatar_hash', 'id_ru', 'id_xyz')

    name: str
    avatar_hash: Optional[str]
    id_ru: Optional[int]
    id_xyz: Optional[int]

    def to_dict(self) -> Dict[str, Union[int, str, None]]:
        return {k: getattr(self, k) for k in ParsedUser.__slots__}


@dataclasses.dataclass
class ParsedComment:
    __slots__ = ('id_ru', 'id_xyz', 'parent_id', 'post_id', 'text', 'user', 'time_posted', 'time_parsed')

    id_ru: Optional[int]
    id_xyz: Optional[int]
    parent_id: Optional[int]
    post_id: int
    text: str
    user: ParsedUser
    time_posted: float
    time_parsed: float
    
    def to_dict(self) -> Dict[str, Union[int, str, float, None]]:
        return dataclasses.asdict(self)

    # TODO: remove/unused
    @staticmethod
    def from_dict(dictionary: Mapping[str, Union[int, str, float, None]]) -> 'ParsedComment':
        slots_set = set(ParsedComment.__slots__)
        dict_set = set(dictionary.keys())

        required_keys = slots_set.difference(dict_set)
        if len(required_keys) > 0:
            raise TypeError(f'Not enough keys: {required_keys} required')

        unexpected_keys = dict_set.difference(slots_set.intersection(dict_set))
        if len(unexpected_keys) > 0:
            raise TypeError(f'Unexpected keys present: {unexpected_keys}')

        return ParsedComment(**dictionary)  # type: ignore

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ParsedComment):
            attrs = set(ParsedComment.__slots__)
            attrs.remove('time_posted')
            attrs.remove('time_parsed')
            return all((
                math.isclose(self.time_posted, other.time_posted),
                all((getattr(self, attr) == getattr(other, attr) for attr in attrs))
            ))
        else:
            return False
    
    # Comments originally posted on govnokod.xyz
    def is_native_xyz_comment(self) -> bool:
        return self.user.id_ru is None


@dataclasses.dataclass
class ParsedPost:
    __slots__ = ('id_ru', 'id_xyz', 'comment_list_id', 'language', 'code', 'text', 'user', 'comments', 'time_posted', 'time_parsed')

    id_ru: Optional[int]
    id_xyz: Optional[int]
    comment_list_id: int
    language: str
    code: str
    text: str
    user: ParsedUser
    comments: List[ParsedComment]
    time_posted: float
    time_parsed: float

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ParsedPost):
            attrs = set(ParsedPost.__slots__)
            attrs.remove('time_posted')
            attrs.remove('time_parsed')
            return all((
                math.isclose(self.time_posted, other.time_posted),
                all((getattr(self, attr) == getattr(other, attr) for attr in attrs))
            ))
        else:
            return False
