import json
import flask
import logging
from datetime import datetime, timezone, timedelta
from schema import ScopedSession, SyncState, User, Post, Comment
from sqlalchemy.sql.expression import func
import re

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


app = flask.Flask(__name__)

def parse_date(date):
    return datetime.strptime(date, DATE_FORMAT)

@app.route('/state')
def state():
    with ScopedSession() as session:
        pending = session.query(SyncState.post_id).filter_by(pending=True).count()
        total = session.query(SyncState.post_id).count()

    return flask.jsonify({
        "pending": pending,
        "total": total
    })

def normalize_text(s):
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

@app.route('/comments')
def comments():
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

        for comment, user, post in query.order_by(Comment.posted.desc()).limit(20).all():
            comments.append({
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
            })

    resp = app.make_response(json.dumps(comments, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp

@app.route('/post/<post_id>')
def post(post_id):
    post_id = int(post_id)

    with ScopedSession() as session:
        post = session.query(Post).get(post_id)
        user = session.query(User).get(post.user_id)

        resp = {
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

        comments = []

        no_comments = flask.request.args.get('no_comments')
        if not no_comments:
            for comment, user in session.query(Comment, User).filter(Comment.post_id == post_id).filter(Comment.user_id == User.user_id).order_by(Comment.posted.asc()).all():
                comments.append({
                    "id": comment.comment_id,
                    "parent_id": comment.parent_id,
                    "post_id": comment.post_id,
                    "text": normalize_text(comment.text),
                    "posted": comment.posted.strftime(DATE_FORMAT),
                    "posted_timestamp": comment.posted.timestamp(),
                    "user_id": user.user_id,
                    "user_name": user.name,
                    "user_avatar": user.avatar_hash,
                    "source": comment.source
                })
        resp["comments"] = comments

        resp = app.make_response(json.dumps(resp, ensure_ascii=False))
        resp.mimetype = 'application/json; charset=utf-8'
        resp.headers['Access-Control-Allow-Origin'] = '*'

        return resp

@app.route('/search')
def search():
    comments = []
    with ScopedSession() as session:
        q = flask.request.args.get('query', '')
        user_name = flask.request.args.get('username', '')
        
        query = session.query(Comment, User, Post, func.ts_headline('russian', Comment.text, func.plainto_tsquery('russian', q), 'HighlightAll=true').label('highlighted')).filter(Comment.user_id == User.user_id).filter(Comment.post_id == Post.post_id)

        if len(q) > 0:
            query = query.filter(Comment.text_tsv.op('@@')(func.plainto_tsquery('russian', q)))
        if len(user_name) > 0:
            query = query.filter(User.name == user_name)
            
        # func.ts_rank_cd(func.to_tsvector('russian', Comment.text), func.plainto_tsquery('russian', q)).desc(), 
        for comment, user, post, highlighted in query.order_by(Comment.posted.desc()).limit(100).all():
            comments.append({
                "id": comment.comment_id,
                "parent_id": comment.parent_id,
                "post_id": comment.post_id,
                "text": normalize_text(highlighted),
                "posted": comment.posted.strftime(DATE_FORMAT),
                "posted_timestamp": comment.posted.timestamp(),
                "user_id": user.user_id,
                "user_name": user.name,
                "user_avatar": user.avatar_hash,
                "comment_list_id": post.comment_list_id,
                "source": comment.source
            })

    resp = app.make_response(json.dumps(comments, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp


@app.route('/users')
def users():
    with ScopedSession() as session:
        query = session.query(User)

        users = []

        for user in query.all():
            users.append({
                "user_id": user.user_id,
                "user_name": user.name,
                "user_avatar": user.avatar_hash
            })

    resp = app.make_response(json.dumps(users, ensure_ascii=False))
    resp.mimetype = 'application/json; charset=utf-8'
    resp.headers['Access-Control-Allow-Origin'] = '*'

    return resp
