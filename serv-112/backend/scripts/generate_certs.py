"""Генерация самоподписанного CA и серверного сертификата для TLS.

Используется для защиты канала admin_tool ↔ backend внутри
изолированного учебного контура (требование ТЗ «Шифрование всех
передаваемых данных (TLS/SSL внутри контура)»).

Раскладка (все файлы — в <repo>/certs/):
    ca.crt      — корневой сертификат (доверенная сторона)
    ca.key      — приватный ключ CA (хранить отдельно, не публиковать)
    server.crt  — сертификат сервера
    server.key  — приватный ключ сервера

Примеры:
    python scripts/generate_certs.py
    python scripts/generate_certs.py --force
    python scripts/generate_certs.py --san 10.0.0.5 --san trainer.local

Зависимость: cryptography.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _find_project_root(start: Path) -> Path:
    """Поднимается вверх до каталога с маркером проекта.

    Маркер: docker-compose.yml либо одновременно admin_tool/ и backend/.
    """
    here = start.resolve()
    for candidate in (here, *here.parents):
        if (candidate / "docker-compose.yml").exists():
            return candidate
        if (candidate / "admin_tool").is_dir() and (candidate / "backend").is_dir():
            return candidate
    return here.parent


PROJECT_ROOT = _find_project_root(Path(__file__).resolve().parent)
CERT_DIR = PROJECT_ROOT / "certs"

CA_CERT_FILE = CERT_DIR / "ca.crt"
CA_KEY_FILE = CERT_DIR / "ca.key"
SERVER_CERT_FILE = CERT_DIR / "server.crt"
SERVER_KEY_FILE = CERT_DIR / "server.key"

CA_DAYS = 3650
SERVER_DAYS = 825
KEY_SIZE = 2048


# --------------------------------------------------------------------- utils

def _atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    if mode is not None:
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
    tmp.replace(path)


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    _atomic_write(
        path,
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        mode=0o600,
    )


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    _atomic_write(path, cert.public_bytes(serialization.Encoding.PEM), mode=0o644)


def _generate_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)


# ------------------------------------------------------------------------ CA

def _build_ca() -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    key = _generate_private_key()
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "System112 Trainer"),
        x509.NameAttribute(NameOID.COMMON_NAME, "System112 Trainer Local CA"),
    ])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


# -------------------------------------------------------------------- server

def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _build_san(names: list[str]) -> x509.SubjectAlternativeName:
    items: list[x509.GeneralName] = []
    seen: set[str] = set()
    for raw in names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            items.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            items.append(x509.DNSName(name))
    if not items:
        items.append(x509.DNSName("localhost"))
        items.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    return x509.SubjectAlternativeName(items)


def _build_server(
    ca_cert: x509.Certificate,
    ca_key: rsa.RSAPrivateKey,
    sans: list[str],
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    key = _generate_private_key()
    common_name = next((s for s in sans if not _is_ip(s)), "localhost")
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "System112 Trainer"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=SERVER_DAYS))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(_build_san(sans), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return cert, key


# ------------------------------------------------------------------------ CLI

def _default_sans() -> list[str]:
    names = ["localhost", "127.0.0.1", "::1"]
    try:
        host = socket.gethostname()
    except Exception:
        return names
    if host and host not in names:
        names.append(host)
    try:
        fqdn = socket.getfqdn(host)
        if fqdn and fqdn not in names:
            names.append(fqdn)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            if ip and ip not in names:
                names.append(ip)
    except Exception:
        pass
    return names


def generate(force: bool, extra_sans: list[str], no_default_sans: bool) -> int:
    if not force and any(
        p.exists() for p in (CA_CERT_FILE, SERVER_CERT_FILE, SERVER_KEY_FILE)
    ):
        print(
            "certs already exist (use --force to overwrite)",
            file=sys.stderr,
        )
        return 1

    sans = [] if no_default_sans else _default_sans()
    sans.extend(extra_sans)

    CERT_DIR.mkdir(parents=True, exist_ok=True)

    ca_cert, ca_key = _build_ca()
    _write_cert(CA_CERT_FILE, ca_cert)
    _write_key(CA_KEY_FILE, ca_key)

    server_cert, server_key = _build_server(ca_cert, ca_key, sans)
    _write_cert(SERVER_CERT_FILE, server_cert)
    _write_key(SERVER_KEY_FILE, server_key)

    print(f"CA cert:     {CA_CERT_FILE}")
    print(f"CA key:      {CA_KEY_FILE}")
    print(f"Server cert: {SERVER_CERT_FILE}")
    print(f"Server key:  {SERVER_KEY_FILE}")
    print(f"SAN:         {', '.join(sans)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Сгенерировать локальный CA и серверный сертификат для TLS.",
    )
    p.add_argument(
        "--force", action="store_true",
        help="перезаписать существующие сертификаты",
    )
    p.add_argument(
        "--san", action="append", default=[], metavar="NAME_OR_IP",
        help="дополнительный SAN (можно указывать несколько раз)",
    )
    p.add_argument(
        "--no-default-sans", action="store_true",
        help="не добавлять автоматически localhost/127.0.0.1/hostname",
    )
    args = p.parse_args(argv)

    print(f"PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"CERT_DIR     = {CERT_DIR}")

    try:
        return generate(args.force, list(args.san), args.no_default_sans)
    except Exception as exc:
        print(f"cert generation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())