"""Bound request-body buffering for multipart essay uploads."""

import json
from tempfile import SpooledTemporaryFile
from typing import Any


class UploadRequestSizeLimitMiddleware:
    def __init__(self, app: Any, *, max_file_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_file_bytes + 64 * 1024

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/v1/essays"
        ):
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > self.max_body_bytes:
                await self._reject(send)
                return

        with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as body:
            total_size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                chunk = message.get("body", b"")
                total_size += len(chunk)
                if total_size > self.max_body_bytes:
                    await self._reject(send)
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break

            body.seek(0)
            sent_final_message = False

            async def replay_body() -> dict[str, Any]:
                nonlocal sent_final_message
                if body.tell() < total_size:
                    chunk = body.read(64 * 1024)
                    more_body = body.tell() < total_size
                    if not more_body:
                        sent_final_message = True
                    return {
                        "type": "http.request",
                        "body": chunk,
                        "more_body": more_body,
                    }
                if not sent_final_message:
                    sent_final_message = True
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                    }
                return {"type": "http.disconnect"}

            await self.app(scope, replay_body, send)

    @staticmethod
    async def _reject(send: Any) -> None:
        payload = json.dumps(
            {"detail": "The upload request exceeds the configured size limit."}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
                "more_body": False,
            }
        )
