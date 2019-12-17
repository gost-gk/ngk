from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import TSVECTOR
from decouple import config


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
    