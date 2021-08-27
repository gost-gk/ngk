import dataclasses
import datetime
from http import HTTPStatus
import logging
import queue
import threading

import pyhocon
import requests
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from ngk.log import get_logger
from ngk.schema import BannedUser, ScopedSession


L = get_logger('denylist_updater', logging.DEBUG)


class _Sentinel:
    pass


_GUARD = _Sentinel()


@dataclasses.dataclass
class Task:
    url: str
    mod_id: str


class DenylistUpdater:
    def __init__(self):
        self._q = queue.Queue(-1)
        self._thread = threading.Thread(target=self._worker, name='DenylistUpdater')
    
    def enqueue_update(self, url: str, mod_id: str) -> None:
        self._q.put_nowait(Task(url=url, mod_id=mod_id))
    
    def start(self) -> None:
        self._thread.start()
    
    def stop(self) -> None:
        self._q.put_nowait(_GUARD)
    
    def join(self, timeout_seconds: float = 5) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout=timeout_seconds)
    
    def _do_update(self, task: Task) -> None:
        L.info('Updating denylist at {}...'.format(task.url))  # TODO
        
        r = requests.get(task.url)
        
        if r.status_code != HTTPStatus.OK:
            L.error('Update url returned {}: {}'.format(r.status_code, r.text))
            return
        
        try:
            hocon = pyhocon.ConfigParser.parse(r.text, resolve=False)
        except:
            L.exception('Exception while parsing HOCON file.')
            return
        
        if not isinstance(hocon, pyhocon.ConfigTree):
            L.error('Update hocon must be a dict with user_id keys.')
            return

        user_ids = list(map(int, hocon.keys()))
        
        with ScopedSession() as session:
            delete_query = (
                delete(BannedUser)
                .where(BannedUser.moderator_id == task.mod_id)
            )
            session.execute(delete_query)
            
            if len(user_ids) > 0:
                ban_date=datetime.datetime.now(tz=datetime.timezone.utc)

                upsert_query = insert(BannedUser).on_conflict_do_update(
                    index_elements=[BannedUser.user_id, BannedUser.moderator_id],
                    set_=dict(ban_date=ban_date)
                )

                session.execute(upsert_query, [{
                        BannedUser.user_id.name: user_id,
                        BannedUser.moderator_id.name: task.mod_id,
                        BannedUser.ban_date.name: ban_date
                    }
                    for user_id in user_ids
                ])
        L.info('Automod {} updated: banned {} users.'.format(task.mod_id, len(user_ids)))
    
    def _worker(self) -> None:
        L.info('DenylistUpdater thread started.')
        
        while True:
            task = self._q.get()
            if task is _GUARD:
                L.info('DenylistUpdater thread received an exit task. Goodbye.')
                return
            
            try:
                self._do_update(task)
            except:
                L.exception('Exception while executing a task.')
