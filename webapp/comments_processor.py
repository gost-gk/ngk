import json
import logging
from typing import List

import redis

from schema import Comment, User, Post, make_comment_dict, make_post_dict


class CommentsProcessor:
    def __init__(self, redis_host, redis_port, redis_password, redis_channel):
        self.redis = redis.Redis(host=redis_host, port=redis_port, password=redis_password)
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.channel = redis_channel

    def subscribe(self):
        self.pubsub.subscribe(self.channel)
    
    def unsubscribe(self):
        self.pubsub.unsubscribe(self.channel)

    def listen(self):
        for msg in self.pubsub.listen():
            try:
                data = msg['data']
            except KeyError:
                continue
            else:
                yield data
    
    def on_post_updated(self, post: Post, users: List[User], comments: List[Comment]):
        logging.debug(f'Listener: got {len(comments)} new comments')
        self._publish(post, users, comments)

    def _publish(self, post: Post, users: List[User], comments: List[Comment]):
        users_dict = {user.user_id: user for user in users}
        published_to = self.redis.publish(self.channel,
            json.dumps([make_comment_dict(comment, users_dict[comment.user_id], post)
                        for comment in comments], ensure_ascii=False).encode('utf-8')
        )
        logging.debug(f'Listener: published to {published_to} channels')
