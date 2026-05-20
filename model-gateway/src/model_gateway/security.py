from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
from dataclasses import dataclass

import bcrypt
from cryptography.fernet import Fernet, InvalidToken


DEV_CREDENTIAL_PREFIX = "dev-plain:"
FERNET_CREDENTIAL_PREFIX = "fernet:"


class CredentialError(ValueError):
    """Raised when a stored vehicle credential cannot be decoded."""


class PasswordPolicyError(ValueError):
    """Raised when a user-supplied password is too weak for competition use."""


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def generate_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_join_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise PasswordPolicyError("Password must be at least 8 characters")
    if password.lower() in {"password", "admin", "deepracer", "12345678"}:
        raise PasswordPolicyError("Password is too easy to guess")


@dataclass(frozen=True)
class CredentialCodec:
    secret: str = ""

    @property
    def is_dev_plaintext(self) -> bool:
        return not bool(self.secret)

    def encrypt(self, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if self.is_dev_plaintext:
            encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
            return DEV_CREDENTIAL_PREFIX + encoded
        token = self._fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return FERNET_CREDENTIAL_PREFIX + token

    def decrypt(self, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if value.startswith(DEV_CREDENTIAL_PREFIX):
            encoded = value[len(DEV_CREDENTIAL_PREFIX):]
            return base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        if value.startswith(FERNET_CREDENTIAL_PREFIX):
            token = value[len(FERNET_CREDENTIAL_PREFIX):]
            try:
                return self._fernet().decrypt(token.encode("ascii")).decode("utf-8")
            except InvalidToken as exc:
                raise CredentialError("Credential secret cannot decrypt stored vehicle credential") from exc
        return value

    def _fernet(self) -> Fernet:
        digest = hashlib.sha256(self.secret.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        return Fernet(key)
