from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class AuditLogger:
    def __init__(self, log_path: str, key_path: str) -> None:
        self.log_path = log_path
        self.key_path = key_path
        self._lock = threading.Lock()
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        os.makedirs(os.path.dirname(self.key_path) or ".", exist_ok=True)

        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read().strip()
            if key:
                return key

        key = Fernet.generate_key()
        with open(self.key_path, "wb") as f:
            f.write(key)
        return key

    def _serialize_entry(
        self,
        event: str,
        diagnosis: str = "",
        confidence: str = "",
        details: str = "",
    ) -> bytes:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "diagnosis": diagnosis,
            "confidence": confidence,
            "details": details,
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def log(
        self,
        event: str,
        diagnosis: str = "",
        confidence: str = "",
        details: str = "",
    ) -> None:
        token = self._fernet.encrypt(
            self._serialize_entry(
                event=event,
                diagnosis=diagnosis,
                confidence=confidence,
                details=details,
            )
        )

        with self._lock:
            os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
            with open(self.log_path, "ab") as f:
                f.write(token + b"\n")

    def read_entries(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.log_path):
            return []

        entries: list[dict[str, Any]] = []
        with open(self.log_path, "rb") as f:
            for line in f:
                token = line.strip()
                if not token:
                    continue
                try:
                    data = self._fernet.decrypt(token)
                    entries.append(json.loads(data.decode("utf-8")))
                except (InvalidToken, json.JSONDecodeError):
                    entries.append(
                        {
                            "timestamp": "",
                            "event": "INVALID_LOG_ENTRY",
                            "diagnosis": "",
                            "confidence": "",
                            "details": "Could not decrypt one log entry.",
                        }
                    )
        return entries