"""Выпуск клиентского сертификата для mTLS.

Запускается один раз на каждое рабочее место администратора. На
сервере достаточно положить ca.crt (уже лежит), на клиенте —
client.crt + client.key + ca.crt.

Использование:
    python scripts/generate_client_cert.py \
        --cn admin-laptop-01 \
        --out ../certs/client
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
CERT_DIR = BACKEND.parent / "certs"

CA_CERT = CERT_DIR / "ca.crt"
CA_KEY = CERT_DIR / "ca.key"

CLIENT_VALID_DAYS = 730  # 2 года

def _load_ca() -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    if not CA_CERT.exists() or not CA_KEY.exists():
        sys.exit(
            f"CA не найден: {CA_CERT} / {CA_KEY}.\n"
            f"Сначала запустите: python scripts/generate_certs.py"
        )
    ca_cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
    ca_key = serialization.load_pem_private_key(
        CA_KEY.read_bytes(), password=None
    )
    return ca_cert, ca_key


def _build_client_cert(
    cn: str, ca_cert: x509.Certificate, ca_key: rsa.RSAPrivateKey,
) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "System-112 Trainer"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])

    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CLIENT_VALID_DAYS))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(cn)]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cn", required=True,
        help="Common Name клиента, например admin-laptop-01",
    )
    parser.add_argument(
        "--out", default=str(CERT_DIR / "client"),
        help="Префикс выходных файлов (без расширения)",
    )
    args = parser.parse_args()

    ca_cert, ca_key = _load_ca()
    cert_pem, key_pem = _build_client_cert(args.cn, ca_cert, ca_key)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cert_path = out.with_suffix(".crt")
    key_path = out.with_suffix(".key")
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    print(f"Клиентский сертификат: {cert_path}")
    print(f"Клиентский ключ:       {key_path}")
    print()
    print("Скопируйте оба файла и ca.crt на рабочее место и пропишите "
          "в .env:")
    print(f"  SSL_CLIENT_CERT_FILE={cert_path}")
    print(f"  SSL_CLIENT_KEY_FILE={key_path}")
    print(f"  SSL_CA_FILE={CA_CERT}")


if __name__ == "__main__":
    main()