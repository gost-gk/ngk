import redis
from decouple import config
from nacl.signing import SigningKey, VerifyKey

from ngk_crypt import get_signing_key, get_verify_key


SECRET_KEY: str = config('SECRET_KEY')

API_PRIVATE_KEY: str = config('API_PRIVATE_KEY')
API_URL: str = config('API_URL').rstrip('/')
API_NONCE_EXPIRATION_SECONDS: int = config('API_NONCE_EXPIRATION_SECONDS', cast=int)

DB_CONNECT_STRING: str = config('DB_CONNECT_STRING')

REDIS_HOST: str = config('REDIS_HOST')
REDIS_PORT: int = config('REDIS_PORT', cast=int)
REDIS_PASSWORD: str = config('REDIS_PASSWORD')
REDIS_CHANNEL: str = config('REDIS_CHANNEL')
REDIS_DB: int = config('REDIS_DB', cast=int)
REDIS_PREFIX: str = config('REDIS_PREFIX')


API_INTERNAL_NAMESPACE: str = '/internal/'

API_ENDPOINT_NONCE_ROUTE: str = API_INTERNAL_NAMESPACE + 'nonce'
API_ENDPOINT_NONCE: str = API_URL + API_ENDPOINT_NONCE_ROUTE

API_ENDPOINT_EVENTS_ROUTE: str = API_INTERNAL_NAMESPACE + 'events'
API_ENDPOINT_EVENTS: str = API_URL + API_ENDPOINT_EVENTS_ROUTE


API_SIGNING_KEY: SigningKey = get_signing_key(API_PRIVATE_KEY)
API_VERIFY_KEY: VerifyKey = get_verify_key(API_SIGNING_KEY)
API_NONCE_SIZE: int = 32
API_NONCE_TIMEOUT_SECONDS: int = 10
