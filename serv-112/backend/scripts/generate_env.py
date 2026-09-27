"""
Генерация .env с безопасным JWT_SECRET.

Запуск (из backend/):
    python scripts/generate_env.py

Если .env уже существует, спросит подтверждение перезаписи.
Файл .env.example не трогается.
"""

import secrets
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    example = root / ".env.example"
    target = root / ".env"

    if not example.exists():
        print(f"error: {example} not found", file=sys.stderr)
        return 1

    if target.exists():
        answer = input(f"{target} already exists. Overwrite? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("aborted")
            return 0

    text = example.read_text(encoding="utf-8")
    secret = secrets.token_urlsafe(64)
    text = text.replace("JWT_SECRET=change-me", f"JWT_SECRET={secret}")
    target.write_text(text, encoding="utf-8")

    print(f"wrote {target}")
    print(f"JWT_SECRET: {secret[:16]}...{secret[-8:]}  ({len(secret)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())