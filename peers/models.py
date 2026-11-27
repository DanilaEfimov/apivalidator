import re
from django.db import models
from django.core.exceptions import ValidationError
from apivalidator.peers.keys import HASH_HEX_LENGTH


__all__ = [
    "Peer",
    "NameValidator",
]


class NameValidator:

    # a name is 1-32 chars, starts and ends with a letter or a digit,
    # and may contain '.', '_' or '-' only between them.
    # anchors ^/$ are kept for readability, but fullmatch() below
    # already requires the whole string to match, so they are redundant
    REGEX: str = "^[a-zA-Z0-9](?:[a-zA-Z0-9._-]{1,30}[a-zA-Z0-9])?$"

    @staticmethod
    def is_valid_name(name: str) -> bool:
        """
        validates a user name against REGEX.
        the pattern is compiled on every call, which is fine for a single
        check but wasteful in a loop; compile once at module level if needed
        :param name: user name
        :return: True if regex satisfied, False otherwise
        """
        pattern = re.compile(NameValidator.REGEX)
        return re.fullmatch(pattern, name) is not None


def is_valid_user_name(name: str) -> None:
    if not NameValidator.is_valid_name(name):
        raise ValidationError(
        "a name is 1-32 chars, starts and ends with a letter or a digit,"
                "and may contain '.', '_' or '-' only between them."
                "anchors ^/$ are kept for readability, but fullmatch() below"
                "already requires the whole string to match, so they are redundant",
                params={"value": name},
            )


class Peer(models.Model):
    """
    peer model.
    frozen, so a peer identity cannot be mutated after it was created:
    the name and the key material are immutable by design,
    revocation is expressed by revoked_at, not by editing the record
    """
    name = models.CharField(max_length=32, unique=True, validators=[is_valid_user_name])   # unique, constant
    hash = models.CharField(max_length=HASH_HEX_LENGTH)   # api-key hash
    prefix = models.CharField(max_length=16, unique=True, db_index=True) # public key prefix
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)    # None by default means an active peer

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

