from comments_processor import CommentsProcessor

import config

processor = CommentsProcessor(config.REDIS_HOST,
                              config.REDIS_PORT,
                              config.REDIS_PASSWORD,
                              config.REDIS_CHANNEL)
processor.subscribe()
for x in processor.listen():
    print(len(x))
