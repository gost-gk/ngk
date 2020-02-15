import json
import logging
from typing import List

import redis

from schema import Comment


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
    
    def on_comments_update(self, new_comments: List[Comment], updated_comments: List[Comment]):
        logging.debug(f'Listener: got {len(new_comments)} new comments and {len(updated_comments)} updated comments')
        published_to = self.redis.publish(
            self.channel,
            json.dumps(
                {
                    'new': [comment.to_dict() for comment in new_comments],
                    'updated': [comment.to_dict() for comment in updated_comments],
                }
                , ensure_ascii=False).encode('utf-8')
        )
        logging.debug(f'Listener: published to {published_to} channels')
