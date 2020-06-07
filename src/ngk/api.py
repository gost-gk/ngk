import eventlet
eventlet.monkey_patch()

from collections import defaultdict, namedtuple
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import secrets
from typing import Dict, Optional, List

import flask
from flask_socketio import SocketIO, close_room, join_room, leave_room
import redis
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import func

from ngk.comments_processor import CommentsProcessor
from ngk import config
from ngk.log import get_logger, redirect_basic_logging
from ngk.schema import Comment, DATE_FORMAT, Post, ScopedSession, SyncState, User


L = get_logger('api', logging.DEBUG)
redirect_basic_logging(L, logging.WARNING)

SEARCH_LIMIT = 50
COMMENTS_LIMIT = 20
RESPONSE_PARENTS_LIMIT = 15
IO_NAMESPACE = '/ngk'

app = flask.Flask(__name__)
app.secret_key = config.SECRET_KEY
io = SocketIO(app, async_mode='eventlet')


def parse_date(date: str) -> datetime:
    return datetime.strptime(date, DATE_FORMAT)


@app.route('/state')
def state() -> flask.Response:
    with ScopedSession() as session:
        pending = session.query(SyncState.post_id).filter_by(pending=True).count()
        total = session.query(SyncState.post_id).count()

    return flask.jsonify({
        "pending": pending,
        "total": total,
        "thread": str(listener_thread)
    })


@app.route('/comments')
def comments() -> flask.Response:
    with ScopedSession() as session:
        query = session.query(Comment)

        id = flask.request.args.get('id')
        if id is not None:
            query = query.filter(Comment.comment_id == id)
        else:
            before = flask.request.args.get('before')
            if before is not None:
                query = query.filter(Comment.posted < parse_date(before))

            ignored_users = flask.request.args.get('ignore_u')
            ignored_posts = flask.request.args.get('ignore_p')
            if ignored_users:
                ignored_users = [int(u) for u in ignored_users.split(',')]
                query = query.filter(Comment.user_id.notin_(ignored_users))
            if ignored_posts:
                ignored_posts = [int(p) for p in ignored_posts.split(',')]
                query = query.filter(Comment.post_id.notin_(ignored_posts))

        comments = []

        for comment in query.order_by(Comment.posted.desc()).limit(COMMENTS_LIMIT).all():
            comments.append(comment.to_dict())

    resp = app.make_response(json.dumps(comments, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


Replies = namedtuple('Replies', ['parents', 'children'])


def get_replies_to(user_id: Optional[int]=None, user_name: Optional[str]=None) -> Replies:
    with ScopedSession() as session:
        if user_id is not None:
            parent_user = session.query(User).filter(User.user_id == user_id).first()
        elif user_name is not None:
            parent_user = session.query(User).filter(User.name == user_name).first()
        else:
            return Replies([], [])
    
        if parent_user is None:
            return Replies([], [])

        query = session.query(Comment) \
            .filter(Comment.children.any()) \
            .filter(Comment.user_id == parent_user.user_id)

        before = flask.request.args.get('before')
        if before is not None:
            query = query.filter(Comment.posted < parse_date(before))

        ignored_posts = flask.request.args.get('ignore_p')
        if ignored_posts:
            ignored_posts = [int(p) for p in ignored_posts.split(',')]
            query = query.filter(Comment.post_id.notin_(ignored_posts))

        parents: List[Comment] = []
        children: List[Comment] = []
        parents = query.order_by(Comment.posted.desc()).limit(RESPONSE_PARENTS_LIMIT).all()
        children = [c for comment in parents for c in comment.children]

        replies = Replies([c.to_dict() for c in parents], [c.to_dict() for c in children])

    return replies


@app.route('/replies/id/<int:user_id>')
def replies_to_id(user_id: int) -> flask.Response:
    resp = app.make_response(json.dumps(get_replies_to(user_id=user_id)._asdict(), ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/replies/name/<user_name>')
def replies_to_name(user_name: str) -> flask.Response:
    resp = app.make_response(json.dumps(get_replies_to(user_name=user_name)._asdict(), ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp
   

@app.route('/post/<int:post_id>')
def post(post_id: int) -> flask.Response:
    with ScopedSession() as session:
        post = session.query(Post).get(post_id)
        resp = post.to_dict()

        comments = []

        no_comments = flask.request.args.get('no_comments')
        if not no_comments:
            for comment in post.comments:
                comments.append(comment.to_dict())
        resp['comments'] = comments

        resp = app.make_response(json.dumps(resp, ensure_ascii=False))
        resp.mimetype = 'application/json; charset=utf-8'
        resp.headers['Access-Control-Allow-Origin'] = '*'

        return resp


@app.route('/search')
def search() -> flask.Response:
    comments = []
    with ScopedSession() as session:
        q: str = flask.request.args.get('query', '').strip()
        try:
            before: Optional[float] = float(flask.request.args.get('before', ''))
        except ValueError:
            before = None

        user_name = flask.request.args.get('username', '')
        
        query = session.query(Comment)
        
        if len(q) > 0:
            if len(q) > 2 and q.startswith('"') and q.endswith('"'):
                query = query.filter(Comment.text.ilike(f'%{q[1:-1]}%'))
            else:
                query = query.filter(Comment.text_tsv.op('@@')(func.plainto_tsquery('russian', q)))
            
        if len(user_name) > 0:
            user_id = session.query(User.user_id).filter(User.name == user_name).scalar()
            query = query.filter(Comment.user_id == user_id)
        
        if before is not None:
            query = query.filter(Comment.posted < datetime.fromtimestamp(before))
        
        for comment in query.order_by(Comment.posted.desc()).limit(SEARCH_LIMIT).all():
            comments.append(comment.to_dict())

    resp = app.make_response(json.dumps(comments, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


@app.route('/user/id/<int:user_id>')
def user_view_id(user_id: int) -> flask.Response:
    with ScopedSession() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        user_dict = {
            'id': user.user_id,
            'name': user.name,
            'avatar': user.avatar_hash
        } if user is not None else {}

    resp = app.make_response(json.dumps(user_dict, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


@app.route('/user/name/<user_name>')
def user_view_name(user_name: str) -> flask.Response:
    with ScopedSession() as session:
        user = session.query(User).filter(User.name == user_name).first()
        user_dict = {
            'id': user.user_id,
            'name': user.name,
            'avatar': user.avatar_hash
        } if user is not None else {}

    resp = app.make_response(json.dumps(user_dict, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


###### SocketIO ######
rooms: Dict[str, int] = {}


@io.on('connect', namespace=IO_NAMESPACE)
def io_connect() -> None:
    L.debug(f'IO: {flask.request.sid} connected')
    rooms[flask.request.sid] = 0
    join_room(flask.request.sid)


@io.on('disconnect', namespace=IO_NAMESPACE)
def io_disconnect() -> None:
    L.debug(f'IO: {flask.request.sid} left')
    close_room(flask.request.sid)
    del rooms[flask.request.sid]


@io.on('set_max_id', namespace=IO_NAMESPACE)
def io_set_max_id(max_id: str) -> None:
    L.debug(f'IO: set_max_id {flask.request.sid} -> {max_id}')
    try:
        max_id_int = int(max_id)
    except ValueError:
        max_id_int = 0
    rooms[flask.request.sid] = max_id_int


def comments_listener(comments_processor: CommentsProcessor) -> None:
    L.debug('IO: CommentsListenerTask started')
    for message in comments_processor.listen():
        try:
            update_event = json.loads(message, encoding='utf-8')
            new_comments = update_event['new']
            updated_comments = update_event['updated']
            L.debug(f'IO: CommentsListenerTask: Got {len(new_comments)} new comments and {len(updated_comments)} updated comments')
            to_send = new_comments + updated_comments
            for room in rooms.copy():
                max_id = rooms[room]
                L.debug(f'IO: CommentsListenerTask: Room {room}, max_id={max_id}, to_send -> {len(to_send)}')
                if len(to_send) > 0:
                    io.emit('new_comments',
                            to_send,
                            namespace=IO_NAMESPACE,
                            room=room)
        except:
            L.exception('IO: CommentsListenerTask: exception')
    L.warning('IO: CommentsListenerTask: exiting')


comments_processor = CommentsProcessor(config.REDIS_HOST,
                                       config.REDIS_PORT,
                                       config.REDIS_PASSWORD,
                                       config.REDIS_CHANNEL,
                                       L)
comments_processor.subscribe()
L.debug('IO: starting CommentsListenerTask')
listener_thread = io.start_background_task(comments_listener, comments_processor)
L.debug('IO: started a listener_thread: ' + str(listener_thread))
