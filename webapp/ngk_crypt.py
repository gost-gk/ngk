from nacl.signing import SigningKey, VerifyKey
import nacl.hash
import nacl.bindings
import nacl.encoding


def get_signing_key(random_password: str) -> SigningKey:
    password_hash_hex = nacl.hash.sha256(random_password.encode('utf-8'))
    password_hash = nacl.encoding.HexEncoder.decode(password_hash_hex)
    assert len(password_hash) == nacl.bindings.crypto_sign_PUBLICKEYBYTES
    return SigningKey(password_hash)
    
def get_verify_key(signing_key: SigningKey) -> VerifyKey:
    return signing_key.verify_key
 