from collections import defaultdict, namedtuple
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import json
import logging
import re

import flask
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import func

from schema import Comment, Post, ScopedSession, SyncState, User


DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SEARCH_LIMIT = 50
COMMENTS_LIMIT = 20

app = flask.Flask(__name__)


def parse_date(date: str) -> datetime:
    return datetime.strptime(date, DATE_FORMAT)


@app.route('/state')
def state() -> flask.Response:
    with ScopedSession() as session:
        pending = session.query(SyncState.post_id).filter_by(pending=True).count()
        total = session.query(SyncState.post_id).count()

    return flask.jsonify({
        "pending": pending,
        "total": total
    })


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


@app.route('/comments')
def comments() -> flask.Response:
    with ScopedSession() as session:
        query = session.query(Comment, User, Post).filter(Comment.user_id == User.user_id).filter(Comment.post_id == Post.post_id)

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

        for comment, user, post in query.order_by(Comment.posted.desc()).limit(COMMENTS_LIMIT).all():
            comments.append(make_comment_dict(comment, user, post))

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

        comment_parent = aliased(Comment)
        query = session.query(Comment, comment_parent, User, Post) \
            .filter(Comment.user_id == User.user_id) \
            .filter(Comment.post_id == Post.post_id) \
            .filter(Comment.user_id != parent_user.user_id) \
            .join(comment_parent, Comment.parent) \
            .filter(comment_parent.user_id == parent_user.user_id)

        before = flask.request.args.get('before')
        if before is not None:
            query = query.filter(Comment.posted < parse_date(before))

        ignore = flask.request.args.get('ignore')
        if ignore is not None:
            ignore = [int(u) for u in ignore.split(',')]
            query = query.filter(Comment.user_id.notin_(ignore))

        parents = {}
        children = []
        for comment, parent_comment, user, post in query.order_by(Comment.posted.desc()).limit(COMMENTS_LIMIT).all():
            if parent_comment.comment_id not in parents:
                parents[parent_comment.comment_id] = make_comment_dict(parent_comment, parent_user, post)
            children.append(make_comment_dict(comment, user, post))
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
        user = session.query(User).get(post.user_id)

        resp = make_post_dict(post, user)

        comments = []

        no_comments = flask.request.args.get('no_comments')
        if not no_comments:
            for comment, user in session.query(Comment, User).filter(Comment.post_id == post_id).filter(Comment.user_id == User.user_id).order_by(Comment.posted.asc()).all():
                comments.append(make_comment_dict(comment, user, post))
        resp["comments"] = comments

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
        
        query = session.query(Comment, User, Post, func.ts_headline('russian', Comment.text, func.plainto_tsquery('russian', q), 'HighlightAll=true').label('highlighted')).filter(Comment.user_id == User.user_id).filter(Comment.post_id == Post.post_id)
        
        if len(q) > 0:
            query = query.filter(Comment.text_tsv.op('@@')(func.plainto_tsquery('russian', q)))
            
        if len(user_name) > 0:
            user_id = session.query(User.user_id).filter(User.name == user_name).scalar()
            query = query.filter(User.user_id == user_id)
        
        if before is not None:
            query = query.filter(Comment.posted < datetime.fromtimestamp(before))
        
        for comment, user, post, highlighted in query.order_by(Comment.posted.desc()).limit(SEARCH_LIMIT).all():
            comments.append(make_comment_dict(comment, user, post))

    resp = app.make_response(json.dumps(comments, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


@app.route('/user/id/<int:user_id>')
def user_view_id(user_id: int) -> flask.Response:
    with ScopedSession() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        user_dict = {
            "id": user.user_id,
            "name": user.name,
            "avatar": user.avatar_hash
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
            "id": user.user_id,
            "name": user.name,
            "avatar": user.avatar_hash
        } if user is not None else {}

    resp = app.make_response(json.dumps(user_dict, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp
