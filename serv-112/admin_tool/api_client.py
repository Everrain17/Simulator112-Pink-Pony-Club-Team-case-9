import logging
import threading
import time

import httpx

from admin_tool import config as app_config
from admin_tool.api_errors import ApiError, raise_for_api
from admin_tool.logging_config import request_id_ctx


logger = logging.getLogger("admin_tool.api")


class _ApiHttpClient(httpx.Client):
    """httpx.Client, который превращает ошибки транспорта и HTTP в ApiError."""

    def send(self, request, **kwargs):
        try:
            response = super().send(request, **kwargs)
        except httpx.TimeoutException as exc:
            raise ApiError("Превышено время ожидания", kind="timeout") from exc
        except httpx.ConnectError as exc:
            text = str(exc)
            low = text.lower()
            if "certificate" in low or "ssl" in low or "tls" in low:
                raise ApiError(
                    f"Ошибка проверки TLS-сертификата сервера: {text}",
                    kind="network",
                ) from exc
            raise ApiError(
                f"Не удалось подключиться к серверу: {text}",
                kind="network",
            ) from exc
        except httpx.RequestError as exc:
            raise ApiError(f"Ошибка сети: {exc}", kind="network") from exc
        raise_for_api(response)
        return response


class ApiClient:
    REFRESH_MARGIN_SEC = 30

    def __init__(
            self,
            server_url: str | None = None,
            *,
            verify: bool | str | None = None,
    ):
        url = (server_url or app_config.server_url()).rstrip("/")
        self.server_url = url
        self.base_url = f"{url}{app_config.API_PREFIX}"

        self.token: str | None = None
        self.refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._token_lock = threading.RLock()

        verify_arg: bool | str = (
            verify if verify is not None else app_config.httpx_verify()
        )

        cert_arg = app_config.httpx_cert()

        self._client = _ApiHttpClient(
            timeout=10,
            verify=verify_arg,
            cert=cert_arg,
            event_hooks={
                "request": [self._on_request],
                "response": [self._on_response],
            },
        )

    # --------------------------------------------------------- event hooks

    def _on_request(self, request: httpx.Request) -> None:
        request.extensions["start_time"] = time.monotonic()
        request_id_ctx.set(None)
        if request.url.path.endswith("/healthz"):
            return
        logger.debug("→ %s %s", request.method, request.url)

    def _on_response(self, response: httpx.Response) -> None:
        rid = response.headers.get("x-request-id")
        if rid:
            request_id_ctx.set(rid)

        path = response.request.url.path
        status = response.status_code

        if path.endswith("/healthz") and status == 200:
            return

        start = response.request.extensions.get("start_time")
        duration_ms = int((time.monotonic() - start) * 1000) if start else None

        method = response.request.method
        msg = "%s %s → %d (%s ms)"
        args = (method, response.request.url, status,
                duration_ms if duration_ms is not None else "?")

        if status >= 500:
            logger.error(msg, *args)
        elif status >= 400:
            logger.warning(msg, *args)
        elif method in ("POST", "PUT", "DELETE", "PATCH"):
            logger.info(msg, *args)
        else:
            logger.debug(msg, *args)

    # ------------------------------------------------------------- auth

    def login(self, username: str, password: str) -> None:
        logger.info("login: user=%s", username)
        try:
            r = self._client.post(
                f"{self.base_url}/auth/login",
                data={"username": username, "password": password},
            )
        except ApiError:
            logger.warning("login rejected: user=%s", username)
            raise
        self._apply_token_payload(r.json())
        logger.info("login ok: user=%s", username)

    def logout(self) -> None:
        with self._token_lock:
            if self.token:
                logger.info("logout (token dropped)")
            self.token = None
            self.refresh_token = None
            self._expires_at = 0.0
        request_id_ctx.set(None)

    def _apply_token_payload(self, payload: dict) -> None:
        with self._token_lock:
            self.token = payload["access_token"]
            self.refresh_token = payload.get("refresh_token")
            expires_in = int(payload.get("expires_in", 900))
            self._expires_at = time.time() + expires_in

    def _refresh_if_needed(self) -> None:
        """Если access скоро истечёт — обновляем через refresh."""
        with self._token_lock:
            if not self.refresh_token:
                return
            if time.time() < self._expires_at - self.REFRESH_MARGIN_SEC:
                return
            refresh_token = self.refresh_token

        logger.debug("access token near expiry — refreshing")
        try:
            r = self._client.post(
                f"{self.base_url}/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        except ApiError:
            logger.warning("token refresh failed — logging out")
            self.logout()
            return
        self._apply_token_payload(r.json())
        logger.debug("token refreshed")

    # ------------------------------------------------------------- health

    def ping(self, timeout: float = 2.0) -> bool:
        try:
            r = self._client.get(
                f"{self.server_url}/healthz",
                timeout=timeout
            )
            return r.status_code == 200
        except Exception as exc:
            logger.debug(
                "ping failed: %s",
                exc,
            )
            return False

    def healthz(self, timeout: float = 2.0) -> dict:
        r = self._client.get(f"{self.server_url}/healthz", timeout=timeout)
        return r.json()

    # ------------------------------------------------------------- admin

    def health(self) -> dict:
        self._refresh_if_needed()
        r = self._client.get(f"{self.base_url}/admin/health", headers=self._headers())
        return r.json()

    def me(self) -> dict:
        self._refresh_if_needed()
        r = self._client.get(f"{self.base_url}/auth/me", headers=self._headers())
        return r.json()

    # ------------------------------------------------------------- scenarios

    def list_scenarios(
            self,
            *,
            search: str | None = None,
            difficulty: int | None = None,
            is_active: bool | None = None,
            page: int = 1,
            size: int = 50,
    ) -> dict:
        params: dict = {"page": page, "size": size}
        if search:
            params["search"] = search
        if difficulty is not None:
            params["difficulty"] = difficulty
        if is_active is not None:
            params["is_active"] = str(is_active).lower()

        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/scenarios", params=params, headers=self._headers()
        )
        return r.json()

    def get_scenario(self, scenario_id: int) -> dict:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/scenarios/{scenario_id}", headers=self._headers()
        )
        return r.json()

    def create_scenario(self, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/scenarios", json=data, headers=self._headers()
        )
        return r.json()

    def update_scenario(self, scenario_id: int, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/scenarios/{scenario_id}",
            json=data,
            headers=self._headers(),
        )
        return r.json()

    def delete_scenario(self, scenario_id: int) -> None:
        self._refresh_if_needed()
        self._client.delete(
            f"{self.base_url}/scenarios/{scenario_id}", headers=self._headers()
        )

    # ------------------------------------------------------------- helpers

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # --------------------------------------------------------------- turns

    def list_turns(self, scenario_id: int) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/scenarios/{scenario_id}/turns",
            headers=self._headers(),
        )
        return r.json()

    def create_turn(self, scenario_id: int, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/scenarios/{scenario_id}/turns",
            json=data, headers=self._headers(),
        )
        return r.json()

    def update_turn(self, scenario_id: int, turn_id: int, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/scenarios/{scenario_id}/turns/{turn_id}",
            json=data, headers=self._headers(),
        )
        return r.json()

    def delete_turn(self, scenario_id: int, turn_id: int) -> None:
        self._refresh_if_needed()
        self._client.delete(
            f"{self.base_url}/scenarios/{scenario_id}/turns/{turn_id}",
            headers=self._headers(),
        )

    def reorder_turns(self, scenario_id: int, ordered_ids: list[int]) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/scenarios/{scenario_id}/turns/reorder",
            json={"ids": ordered_ids}, headers=self._headers(),
        )
        return r.json()

    # ---------------------------------------------------------- classifiers

    def list_services(self) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/classifiers/services", headers=self._headers()
        )
        return r.json()

    def list_incident_types(self, service_code: str | None = None) -> list[dict]:
        self._refresh_if_needed()
        params = {"service_code": service_code} if service_code else None
        r = self._client.get(
            f"{self.base_url}/classifiers/incident-types",
            params=params, headers=self._headers(),
        )
        return r.json()

    def list_dialog_stages(self) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/classifiers/dialog-stages", headers=self._headers()
        )
        return r.json()

    def list_emotional_states(self) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/classifiers/emotional-states", headers=self._headers()
        )
        return r.json()

    # ----------------------------------------------------------------- cards

    def list_cards(
        self,
        *,
        search: str | None = None,
        incident_type_code: str | None = None,
        source: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict:
        params: dict = {"page": page, "size": size}
        if search:
            params["search"] = search
        if incident_type_code:
            params["incident_type_code"] = incident_type_code
        if source:
            params["source"] = source

        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/cards", params=params, headers=self._headers()
        )
        return r.json()

    def get_card(self, card_id: int) -> dict:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/cards/{card_id}", headers=self._headers()
        )
        return r.json()

    def create_card(self, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/cards", json=data, headers=self._headers()
        )
        return r.json()

    def update_card(self, card_id: int, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/cards/{card_id}", json=data, headers=self._headers()
        )
        return r.json()

    def delete_card(self, card_id: int) -> None:
        self._refresh_if_needed()
        self._client.delete(
            f"{self.base_url}/cards/{card_id}", headers=self._headers()
        )

    # ----------------------------------------------------------------- users

    def list_users(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict:
        params: dict = {"page": page, "size": size}
        if search:
            params["search"] = search
        if role:
            params["role"] = role
        if is_active is not None:
            params["is_active"] = str(is_active).lower()

        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/users", params=params, headers=self._headers()
        )
        return r.json()

    def get_user(self, user_id: int) -> dict:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/users/{user_id}", headers=self._headers()
        )
        return r.json()

    def create_user(self, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/users", json=data, headers=self._headers()
        )
        return r.json()

    def update_user(self, user_id: int, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/users/{user_id}", json=data, headers=self._headers()
        )
        return r.json()

    def deactivate_user(self, user_id: int) -> None:
        self._refresh_if_needed()
        self._client.delete(
            f"{self.base_url}/users/{user_id}", headers=self._headers()
        )

    def reset_user_password(self, user_id: int) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/users/{user_id}/reset-password",
            headers=self._headers(),
        )
        return r.json()

    # ---------------------------------------------------------------- traces

    def list_traces(
        self,
        *,
        scenario_id: int | None = None,
        operator_id: int | None = None,
        is_reference: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict:
        params: dict = {"page": page, "size": size}
        if scenario_id is not None:
            params["scenario_id"] = scenario_id
        if operator_id is not None:
            params["operator_id"] = operator_id
        if is_reference is not None:
            params["is_reference"] = str(is_reference).lower()

        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/traces", params=params, headers=self._headers()
        )
        return r.json()

    def get_trace(self, trace_id: int) -> dict:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/traces/{trace_id}", headers=self._headers()
        )
        return r.json()

    def create_trace(self, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/traces", json=data, headers=self._headers()
        )
        return r.json()

    def update_trace(self, trace_id: int, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/traces/{trace_id}", json=data, headers=self._headers()
        )
        return r.json()

    def delete_trace(self, trace_id: int) -> None:
        self._refresh_if_needed()
        self._client.delete(
            f"{self.base_url}/traces/{trace_id}", headers=self._headers()
        )

    # ----------------------------------------------------------------- audit

    def list_audit(
        self,
        *,
        category: str | None = None,
        username: str | None = None,
        action: str | None = None,
        level: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict:
        params: dict = {"page": page, "size": size}
        if category: params["category"] = category
        if username: params["username"] = username
        if action:   params["action"] = action
        if level:    params["level"] = level
        if since:    params["since"] = since
        if until:    params["until"] = until

        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/audit", params=params, headers=self._headers()
        )
        return r.json()

    def list_audit_categories(self) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/audit/categories", headers=self._headers()
        )
        return r.json()

    def cleanup_audit(self, older_than_days: int) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/audit/cleanup",
            json={"older_than_days": older_than_days},
            headers=self._headers(),
        )
        return r.json()

    # -------------------------------------------------------------- settings

    def get_settings(self) -> dict:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/settings", headers=self._headers()
        )
        return r.json()

    def update_settings(self, data: dict) -> dict:
        self._refresh_if_needed()
        r = self._client.put(
            f"{self.base_url}/settings", json=data, headers=self._headers()
        )
        return r.json()

    # ------------------------------------------------------------- system

    def system_info(self) -> dict:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/admin/system/info", headers=self._headers()
        )
        return r.json()

    # ------------------------------------------------------------- backups

    BACKUP_TIMEOUT = 600.0

    def list_backups(self) -> list[dict]:
        self._refresh_if_needed()
        r = self._client.get(
            f"{self.base_url}/admin/backups", headers=self._headers()
        )
        return r.json()

    def create_backup(self) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/admin/backups",
            headers=self._headers(),
            timeout=self.BACKUP_TIMEOUT,
        )
        return r.json()

    def restore_backup(self, backup_id: int) -> dict:
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/admin/backups/{backup_id}/restore",
            headers=self._headers(),
            timeout=self.BACKUP_TIMEOUT,
        )
        return r.json()

    def delete_backup(self, backup_id: int) -> None:
        self._refresh_if_needed()
        self._client.delete(
            f"{self.base_url}/admin/backups/{backup_id}",
            headers=self._headers(),
        )

    def reconcile_backups(self) -> dict:
        """Принудительная синхронизация backup_records с файлами на диске."""
        self._refresh_if_needed()
        r = self._client.post(
            f"{self.base_url}/admin/backups/reconcile",
            headers=self._headers(),
        )
        return r.json()