from contextlib import contextmanager
import re
from typing import Dict

from decouple import config
from sqlalchemy import create_engine
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker


engine = create_engine(config('DB_CONNECT_STRING'))
Base = declarative_base()
Session = sessionmaker()
Session.configure(bind=engine)


@contextmanager
def ScopedSession():
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


class SyncState(Base):
    __tablename__ = 'sync_states'

    post_id = Column(Integer, primary_key=True)
    last_comment_id = Column(Integer)
    pending = Column(Boolean)
    priority = Column(Integer)
    synced = Column(DateTime)
    result = Column(String)

    PRIORITY_HAS_COMMENTS = 10
    PRIORITY_DUMP = 9


class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True)
    name = Column(String)
    avatar_hash = Column(String)
    source = Column(Integer)

    SOURCE_GK = 0
    SOURCE_WEBARCHIVE = 1
    SOURCE_XYZ = 2
    
    
class Post(Base):
    __tablename__ = 'posts'

    post_id = Column(Integer, primary_key=True)
    comment_list_id = Column(Integer)
    user_id = Column(Integer)
    language = Column(String)
    code = Column(String)
    text = Column(String)
    text_tsv = Column(TSVECTOR)
    posted = Column(DateTime)
    vote_plus = Column(Integer)
    vote_minus = Column(Integer)
    rating = Column(Numeric)
    source = Column(Integer)

    SOURCE_GK = 0
    SOURCE_WEBARCHIVE = 1
    SOURCE_XYZ = 2
    
    
class Comment(Base):
    __tablename__ = 'comments'

    comment_id = Column(Integer, primary_key=True)
    comment_id_xyz = Column(Integer)
    post_id = Column(Integer)
    parent_id = Column(Integer, ForeignKey('comments.comment_id'))
    parent = relationship('Comment', uselist=False, remote_side=[comment_id])
    user_id = Column(Integer)
    text = Column(String)
    text_tsv = Column(TSVECTOR)
    posted = Column(DateTime)
    vote_plus = Column(Integer)
    vote_minus = Column(Integer)
    rating = Column(Numeric)
    source = Column(Integer)

    SOURCE_GK = 0
    SOURCE_WEBARCHIVE = 1
    SOURCE_XYZ = 2


# TODO: shit. Move to a standalone
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def normalize_text(s: str) -> str:
    # TODO: hacks below should be integrated into the parser
    s = s.replace("&#13;", "")

    res = ""
    while True:
        m = re.search(r'<a.*?data-cfemail="(.*?)">.*?</a>', s)
        if not m:
            break

        encoded = bytes.fromhex(m.group(1))
        key = encoded[0]
        decoded = "".join([chr(c ^ key) for c in encoded[1:]])

        res += s[:m.start()]
        res += decoded
        s = s[m.end():]

    return res + s


def make_comment_dict(comment: Comment, user: User, post: Post) -> Dict:
    return {
        "id": comment.comment_id,
        "parent_id": comment.parent_id,
        "post_id": comment.post_id,
        "text": normalize_text(comment.text),
        "posted": comment.posted.strftime(DATE_FORMAT),
        "posted_timestamp": comment.posted.timestamp(),
        "user_id": user.user_id,
        "user_name": user.name,
        "user_avatar": user.avatar_hash,
        "comment_list_id": post.comment_list_id,
        "source": comment.source
    }


def make_post_dict(post: Post, user: User) -> Dict:
    return {
        "id": post.post_id,
        "code": post.code,
        "text": normalize_text(post.text),
        "posted": post.posted.strftime(DATE_FORMAT),
        "posted_timestamp": post.posted.timestamp(),
        "user_id": user.user_id,
        "user_name": user.name,
        "user_avatar": user.avatar_hash,
        "comment_list_id": post.comment_list_id,
        "source": post.source
    }
