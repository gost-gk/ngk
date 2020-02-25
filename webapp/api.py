import eventlet
eventlet.monkey_patch()

from collections import defaultdict, namedtuple
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import secrets
from typing import Dict, Optional

import flask
from flask_socketio import SocketIO, close_room, join_room, leave_room
import redis
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import func

from comments_processor import CommentsProcessor
import config
from schema import Comment, DATE_FORMAT, Post, ScopedSession, SyncState, User


SEARCH_LIMIT = 50
COMMENTS_LIMIT = 20
IO_NAMESPACE = '/ngk'

app = flask.Flask(__name__)
app.secret_key = config.SECRET_KEY
io = SocketIO(app, async_mode='eventlet')


logging.basicConfig(
    filename="../logs/api.log",
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG)


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

            ignore = flask.request.args.get('ignore')
            if ignore:
                ignore = [int(u) for u in ignore.split(',')]
                query = query.filter(Comment.user_id.notin_(ignore))

        comments = []

        for comment in query.order_by(Comment.posted.desc()).limit(COMMENTS_LIMIT).all():
            comments.append(comment.to_dict())

    resp = app.make_response(json.dumps(comments, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


Replies = namedtuple('Replies', ['parents', 'children'])
Replies.__new__.__defaults__ = ([], [])
def get_replies_to(user_id: Optional[int]=None, user_name: Optional[str]=None) -> Replies:
    with ScopedSession() as session:
        if user_id is not None:
            parent_user = session.query(User).filter(User.user_id == user_id).first()
        elif user_name is not None:
            parent_user = session.query(User).filter(User.name == user_name).first()
        else:
            return Replies()
    
        if parent_user is None:
            return Replies()

        Comment_parent = aliased(Comment)
        query = session.query(Comment, Comment_parent) \
            .filter(Comment.user_id != parent_user.user_id) \
            .join(Comment_parent, Comment.parent) \
            .filter(Comment_parent.user_id == parent_user.user_id)

        before = flask.request.args.get('before')
        if before is not None:
            query = query.filter(Comment.posted < parse_date(before))

        ignore = flask.request.args.get('ignore')
        if ignore is not None:
            ignore = [int(u) for u in ignore.split(',')]
            query = query.filter(Comment.user_id.notin_(ignore))

        parents = {}
        children = []
        for comment, parent_comment in query.order_by(Comment.posted.desc()).limit(COMMENTS_LIMIT).all():
            if parent_comment.comment_id not in parents:
                parents[parent_comment.comment_id] = parent_comment.to_dict()
            children.append(comment.to_dict())
        replies = Replies(
            list(parents.values()),
            children
        )

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
        q = flask.request.args.get('query', '')
        try:
            before = float(flask.request.args.get('before', ''))
        except ValueError:
            before = None

        user_name = flask.request.args.get('username', '')
        
        query = session.query(Comment)
        
        if len(q) > 0:
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
def io_connect():
    logging.debug(f'IO: {flask.request.sid} connected')
    rooms[flask.request.sid] = 0
    join_room(flask.request.sid)


@io.on('disconnect', namespace=IO_NAMESPACE)
def io_disconnect():
    logging.debug(f'IO: {flask.request.sid} left')
    close_room(flask.request.sid)
    del rooms[flask.request.sid]


@io.on('set_max_id', namespace=IO_NAMESPACE)
def io_set_max_id(max_id):
    logging.debug(f'IO: set_max_id {flask.request.sid} -> {max_id}')
    try:
        max_id = int(max_id)
    except ValueError:
        max_id = 0
    rooms[flask.request.sid] = max_id


def comments_listener(comments_processor: CommentsProcessor):
    logging.debug('IO: CommentsListenerTask started')
    for message in comments_processor.listen():
        try:
            update_event = json.loads(message, encoding='utf-8')
            new_comments = update_event['new']
            updated_comments = update_event['updated']
            logging.debug(f'IO: CommentsListenerTask: Got {len(new_comments)} new comments and {len(updated_comments)} updated comments')
            to_send = new_comments + updated_comments
            for room in rooms.copy():
                max_id = rooms[room]
                logging.debug(f'IO: CommentsListenerTask: Room {room}, max_id={max_id}, to_send -> {len(to_send)}')
                if len(to_send) > 0:
                    io.emit('new_comments',
                            to_send,
                            namespace=IO_NAMESPACE,
                            room=room)
        except:
            logging.exception('IO: CommentsListenerTask: exception')
    logging.warning('IO: CommentsListenerTask: exiting')


comments_processor = CommentsProcessor(config.REDIS_HOST,
                                       config.REDIS_PORT,
                                       config.REDIS_PASSWORD,
                                       config.REDIS_CHANNEL)
comments_processor.subscribe()
logging.debug('IO: starting CommentsListenerTask')
listener_thread = io.start_background_task(comments_listener, comments_processor)
logging.debug('IO: started a listener_thread: ' + str(listener_thread))
