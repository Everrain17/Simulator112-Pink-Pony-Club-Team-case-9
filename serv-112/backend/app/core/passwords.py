import secrets
import string

_ALPHABET = string.ascii_letters + string.digits

def generate_password(length: int = 12) -> str:
    """Случайный пароль с хорошей энтропией. Используется при сбросе."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))