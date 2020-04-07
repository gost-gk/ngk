from ngk import config
from ngk.comments_processor import CommentsProcessor


processor = CommentsProcessor(config.REDIS_HOST,
                              config.REDIS_PORT,
                              config.REDIS_PASSWORD,
                              config.REDIS_CHANNEL)
processor.subscribe()
for x in processor.listen():
    print(len(x))
