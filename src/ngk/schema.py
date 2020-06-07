from contextlib import contextmanager
import re
from typing import Any, Dict, Iterator

from sqlalchemy import create_engine, event
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy.orm
from sqlalchemy.orm import relationship, sessionmaker, deferred

from ngk import config
from ngk.html_util import normalize_text



DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

engine = create_engine(config.DB_CONNECT_STRING)
Base = declarative_base()
Session = sessionmaker()
Session.configure(bind=engine)


@contextmanager
def ScopedSession() -> Iterator[sqlalchemy.orm.Session]:
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

    comments = relationship('Comment', back_populates='user', order_by='Comment.posted.asc()')
    posts = relationship('Post', back_populates='user', order_by='Post.posted.asc()')

    SOURCE_GK = 0
    SOURCE_WEBARCHIVE = 1
    SOURCE_XYZ = 2
    
    
class Post(Base):
    __tablename__ = 'posts'

    post_id = Column(Integer, primary_key=True)
    comment_list_id = Column(Integer)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    user = relationship('User', lazy='joined', back_populates='posts')
    language = deferred(Column(String))
    code = deferred(Column(String))
    text = deferred(Column(String))
    text_tsv = deferred(Column(TSVECTOR))
    posted = Column(DateTime)
    vote_plus = deferred(Column(Integer))
    vote_minus = deferred(Column(Integer))
    rating = deferred(Column(Numeric))
    source = Column(Integer)

    comments = relationship('Comment', back_populates='post', order_by='Comment.posted.asc()')

    SOURCE_GK = 0
    SOURCE_WEBARCHIVE = 1
    SOURCE_XYZ = 2
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.post_id,
            'code': self.code,
            'text': normalize_text(self.text or ''),
            'posted': self.posted.strftime(DATE_FORMAT) if self.posted is not None else None,
            'posted_timestamp': self.posted.timestamp() if self.posted is not None else None,
            'user_id': self.user_id,
            'user_name': self.user.name,
            'user_avatar': self.user.avatar_hash,
            'comment_list_id': self.comment_list_id,
            'source': self.source
        }

    
class Comment(Base):
    __tablename__ = 'comments'

    comment_id = Column(Integer, ForeignKey('comment_ids_storage.comment_id_ru'), primary_key=True)
    comment_id_storage = relationship('CommentIdStorage', lazy='joined', foreign_keys=[comment_id], uselist=False, cascade='')

    post_id = Column(Integer, ForeignKey('posts.post_id'))
    post = relationship('Post', lazy='joined', back_populates='comments')
    parent_id = Column(Integer, ForeignKey('comments.comment_id'))
    parent = relationship('Comment', uselist=False, remote_side=[comment_id])
    children = relationship('Comment', uselist=True, remote_side=[parent_id])
    user_id = Column(Integer, ForeignKey('users.user_id'))
    user = relationship('User', lazy='joined', back_populates='comments')
    text = Column(String)
    text_tsv = deferred(Column(TSVECTOR))
    posted = Column(DateTime)
    vote_plus = deferred(Column(Integer))
    vote_minus = deferred(Column(Integer))
    rating = deferred(Column(Numeric))
    source = Column(Integer)

    SOURCE_GK = 0
    SOURCE_WEBARCHIVE = 1
    SOURCE_XYZ = 2

    def __init__(self, comment_id: int):
        self.comment_id = comment_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.comment_id,
            'id_xyz': self.comment_id_storage.comment_id_xyz if self.comment_id_storage is not None else None,
            'parent_id': self.parent_id,
            'post_id': self.post_id,
            'text': normalize_text(self.text or ''),
            'posted': self.posted.strftime(DATE_FORMAT) if self.posted is not None else None,
            'posted_timestamp': self.posted.timestamp() if self.posted is not None else None,
            'user_id': self.user_id,
            'user_name': self.user.name,
            'user_avatar': self.user.avatar_hash,
            'comment_list_id': self.post.comment_list_id,
            'source': self.source
        }


class CommentIdStorage(Base):
    __tablename__ = 'comment_ids_storage'

    comment_id_ru = Column(Integer, primary_key=True)
    comment_id_xyz = Column(Integer)

