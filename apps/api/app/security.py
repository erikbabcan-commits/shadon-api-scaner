from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def make_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.straz_session_secret, salt="straz-session")


def create_session_token(settings: Settings, user_id: str, token_version: int = 1) -> str:
    return make_serializer(settings).dumps({"uid": user_id, "ver": token_version})


def read_session_token(settings: Settings, token: str) -> dict[str, any] | None:
    try:
        data = make_serializer(settings).loads(token, max_age=settings.straz_session_max_age)
        if not isinstance(data, dict) or "uid" not in data:
            return None
        return {"uid": str(data["uid"]), "ver": int(data.get("ver", 1))}
    except (BadSignature, SignatureExpired, Exception):
        return None
