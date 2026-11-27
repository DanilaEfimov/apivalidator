"""
dummy hash with same length as a real hash
#TODO: papper maybe
"""
import hashlib

HASH_ALGO = hashlib.sha256
HASH_HEX_LENGTH = len(HASH_ALGO().hexdigest())

def hash_secret(secret: str) -> str:
    """
    generates sha256 hash. It's required by a constant hash length constraint
    :param secret:
    :return:
    """
    return HASH_ALGO(secret.encode()).hexdigest()

DUMMY_HASH = HASH_ALGO(b"dummy").hexdigest()
