#/usr/bin/env python3
import logging
import time

from sqlalchemy.sql.expression import func

from ngk.schema import Comment, Post, ScopedSession, User
from ngk.html_util import normalize_text


def main():
    BATCH_SIZE = 50000
    total_count = 0
    with ScopedSession() as session:
        offset = 0
        db_comments_count = session.query(func.count(Comment.comment_id)).scalar()
        parsed_comments = set()
        while True:
            print(f'Offset: {offset}')
            q = session.query(Comment).order_by(Comment.comment_id).limit(BATCH_SIZE).offset(offset)
            for comment in q:
                comment.text = normalize_text(comment.text)
                parsed_comments.add(comment.comment_id)
                total_count += 1
            offset += BATCH_SIZE
            if offset > db_comments_count:
                break
    print(f'Total_count: {total_count}, db_count: {db_comments_count}, parsed_comments_len: {len(parsed_comments)}')


if __name__ == '__main__':
    main()
