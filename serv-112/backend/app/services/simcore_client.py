from typing import Any

import httpx

from app.config import settings


class SimCoreError(RuntimeError):
    pass


class SimCoreClient:
    def __init__(self) -> None:
        self.base_url = settings.SIMCORE_URL.rstrip("/")
        self.timeout = settings.SIMCORE_TIMEOUT_SEC

        self.headers = {
            "X-System112-Internal": settings.SIMCORE_INTERNAL_TOKEN,
        }

        if settings.SSL_ENABLED:
            self.verify: str | bool = str(settings.SSL_CA_FILE)
        else:
            self.verify = True

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}{path}"

        headers = dict(self.headers)
        headers.update(
            kwargs.pop("headers", {}) or {}
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.verify,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                )

        except httpx.HTTPError as exc:
            raise SimCoreError(
                f"SimCore недоступен: {exc}"
            ) from exc

        if not response.is_success:
            text = response.text[:1500]

            raise SimCoreError(
                f"SimCore вернул HTTP "
                f"{response.status_code}: {text}"
            )

        try:
            return response.json()

        except ValueError as exc:
            raise SimCoreError(
                "SimCore вернул некорректный JSON"
            ) from exc

    async def classifier(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/classifier",
        )

    async def state(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/state",
        )

    async def available_calls(self) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/available-calls",
        )

    async def accept_call(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/accept-call",
            json=payload,
        )

    async def inject(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/inject",
            json=payload,
        )

    async def teacher_intervene(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/teacher-intervene",
            json=payload,
        )

    async def start(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/start",
            json=payload,
        )

    async def stop(self) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/stop",
            json={},
        )

    async def complete_call(
        self,
        call_id: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/complete-call",
            json={
                "callId": call_id
            }
        )

    async def snapshot(self, call_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/call-snapshot/{call_id}",
        )
        
    async def release_call(
        self,
        call_id: str,) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/release-call",
            json={
                "callId": call_id,
            },
        )