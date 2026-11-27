import hmac
from typing import Tuple, Optional
from rest_framework.request import Request
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from apivalidator.peers.models import Peer
from apivalidator.peers.keys import *


class PeerAuthentication(BaseAuthentication):
    """
    authenticates a peer by the api key from the request header.
    the key looks like '<public prefix>:<secret>': the prefix is not secret
    and is used to find the candidate in the db, the secret is compared
    with the stored hash in constant time.
    a missing header gives None (the request stays anonymous),
    a wrong key always gives the same 401, whatever the reason was
    """

    ERROR = "Invalid or missing API key"

    def authenticate_header(self, request) -> str:
        """
        scheme name for the WWW-Authenticate header of a 401 response.
        also used as the name of the header the key is read from.
        without it DRF answers 403 instead of 401
        :param request: request being authenticated (unused)
        :return: header name
        """
        return "AV-API-Key"

    def authenticate(self, request: Request) -> Optional[Tuple[Peer, None]]:
        """
        entry point called by DRF: finds the peer that owns the key
        :param request: rest_framework.request.Request
        :return: (peer, None), peer goes to request.user,
                 or None if the key header is absent
        :raises AuthenticationFailed: if the key is present but does not match any peer
        """
        raw = request.headers.get(self.authenticate_header(request))
        if not raw:
            return None

        prefix, _, secret = self.select_parts(raw)

        candidate = self.select_candidate(prefix)
        if candidate is None:
            # no such prefix: still hash and compare with a dummy,
            # so the response time does not reveal that the prefix is unknown
            _ = hmac.compare_digest(hash_secret(secret), DUMMY_HASH)
            raise AuthenticationFailed(self.ERROR)

        peer = self.compare_secrets(candidate, secret)
        if peer is None:
            # wrong secret: same error as for an unknown prefix
            _ = hmac.compare_digest(hash_secret(secret), DUMMY_HASH)
            raise AuthenticationFailed(self.ERROR)

        return peer, None

    @staticmethod
    def select_parts(raw: str) -> Tuple[str, ...]:
        """
        splits the raw key by the first ':' into prefix and secret.
        if there is no ':' the prefix is the whole string and the secret is empty,
        which ends in a regular 401 and not in an exception
        :param raw: header value as is
        :return: (prefix, separator, secret)
        """
        return raw.partition(":")

    @staticmethod
    def select_candidate(public: str):
        """
        looks the peer up by the public prefix of the key.
        the secret is not involved here, hashes are compared separately
        :param public: public prefix of the key
        :return: the peer, or None if there is no such prefix
        """
        return Peer.objects.filter(filter=public).first()

    @staticmethod
    def compare_secrets(candidate: Peer, secret: str) -> Peer | None:
        """
        compares the given secret with the candidate's stored hash.
        uses hmac.compare_digest, so the time does not depend on
        where the strings differ
        :param candidate: peer found by the prefix
        :param secret: secret part of the key from the request
        :return: candidate if the secret is right, None otherwise
        """
        if not hmac.compare_digest(hash_secret(secret), candidate.hash):
            return None
        return candidate
