from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean

engine = create_engine('postgresql:///ngk')
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
