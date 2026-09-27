from __future__ import annotations
import argparse
import logging
import ssl
import uvicorn
from app.config import settings
logger = logging.getLogger("app.server")
_TLS12_CIPHERS = ":".join([
    "ECDHE-ECDSA-AES128-GCM-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-CHACHA20-POLY1305",
    "DHE-RSA-AES128-GCM-SHA256",
    "DHE-RSA-AES256-GCM-SHA384",
    "DHE-RSA-CHACHA20-POLY1305",
])
_TLS13_CIPHERS = ":".join([
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
    "TLS_AES_128_GCM_SHA256",
])
def _build_ssl_context() -> ssl.SSLContext | None:
    if not settings.SSL_ENABLED:
        logger.warning(
            "SSL_ENABLED=false — backend стартует без TLS. "
            "Это допустимо только в отладке."
        )
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if settings.SSL_MIN_TLS_VERSION == "1.3":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    else:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(_TLS12_CIPHERS)
    tls13_status = "n/a"
    if ssl.HAS_TLSv1_3:
        set_ciphersuites = getattr(ctx, "set_ciphersuites", None)
        if set_ciphersuites is None:
            logger.warning(
                "SSLContext.set_ciphersuites недоступен — используются "
                "дефолтные TLS 1.3 cipher suites OpenSSL",
            )
            tls13_status = "по умолчанию"
        else:
            try:
                set_ciphersuites(_TLS13_CIPHERS)
                tls13_status = "задан"
            except ssl.SSLError as exc:
                logger.warning(
                    "set_ciphersuites отклонён OpenSSL (%s) — "
                    "используются дефолтные TLS 1.3 cipher suites",
                    exc,
                )
                tls13_status = "по умолчанию"
    ctx.options |= ssl.OP_NO_COMPRESSION
    ctx.options |= ssl.OP_NO_TICKET
    if hasattr(ssl, "OP_NO_RENEGOTIATION"):
        ctx.options |= ssl.OP_NO_RENEGOTIATION
    ctx.load_cert_chain(
        certfile=str(settings.SSL_CERT_FILE),
        keyfile=str(settings.SSL_KEY_FILE),
    )
    if settings.SSL_VERIFY_CLIENT:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=str(settings.SSL_CA_FILE))
        logger.info(
            "mTLS включён: клиент обязан предъявить сертификат, "
            "подписанный %s", settings.SSL_CA_FILE,
        )
    else:
        ctx.verify_mode = ssl.CERT_NONE
        logger.info("mTLS выключен: проверяется только серверный сертификат")
    logger.info(
        "TLS готов: min_version=%s, ciphers(TLS≤1.2)=%d шт., "
        "ciphers(TLS 1.3)=%s",
        settings.SSL_MIN_TLS_VERSION,
        len(_TLS12_CIPHERS.split(":")),
        tls13_status,
    )
    return ctx
def _install_ssl_context(ssl_ctx: ssl.SSLContext | None) -> None:
    if ssl_ctx is None:
        return
    import uvicorn.config as uvicorn_config
    import uvicorn.server as uvicorn_server
    def _create_ssl_context(*args, **kwargs):
        return ssl_ctx
    if hasattr(uvicorn_server, "create_ssl_context"):
        uvicorn_server.create_ssl_context = _create_ssl_context
    if hasattr(uvicorn_config, "create_ssl_context"):
        uvicorn_config.create_ssl_context = _create_ssl_context
    logger.info("SSLContext передан в uvicorn")
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="app.server",
        description="uvicorn с TLS-контекстом из app.config",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=settings.SERVER_PORT)
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    ssl_ctx = _build_ssl_context()
    _install_ssl_context(ssl_ctx)
    config = uvicorn.Config(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        ssl_certfile=str(settings.SSL_CERT_FILE) if ssl_ctx else None,
        ssl_keyfile=str(settings.SSL_KEY_FILE) if ssl_ctx else None,
        proxy_headers=False,
    )
    server = uvicorn.Server(config)
    server.run()
if __name__ == "__main__":
    main()