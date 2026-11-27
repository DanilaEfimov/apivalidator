from dataclasses import dataclass
from datetime import datetime
import re


__all__ = [
    "Peer",
    "NameValidator",
]


@dataclass(frozen=True)
class Peer:
    """
    peer model.
    frozen, so a peer identity cannot be mutated after it was created:
    the name and the key material are immutable by design,
    revocation is expressed by revoked_at, not by editing the record
    """
    name: str   # unique, constant
    hash: str   # api-key hash
    prefix: str # public key prefix
    created_at: datetime
    revoked_at: datetime | None = None    # None by default means an active peer


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
