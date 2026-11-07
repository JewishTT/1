"""Encrypted, redacted, retention-bound captured artifacts.

A captured artifact is the highest-risk object in the platform. It is encrypted with
AES-256-GCM before it enters the store, and the API never receives the key or the
plaintext: `view()` returns a preview like `session ••••`. `reveal()` exists for tests and
retention verification only, is not routed, and appends an access-audit row.
"""

from __future__ import annotations

import base64
import hashlib
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from specops.lab.audit import AuditLog
from specops.lab.boundary import LabError, LabNotFound, SetupRequired
from specops.lab.models import Artifact, ArtifactKind, now_iso

KEY_ENV = "SPECOPS_LAB_ARTIFACT_KEY"
ALGORITHM = "AES-256-GCM"


def _decode_key(raw: str) -> bytes:
    text = raw.strip()
    try:
        if len(text) == 64:
            key = bytes.fromhex(text)
        else:
            padded = text + ("=" * (-len(text) % 4))
            key = base64.urlsafe_b64decode(padded)
    except Exception as exc:  # noqa: BLE001 - a malformed key is a setup fact
        raise SetupRequired(
            f"{KEY_ENV} is not valid hex or base64url; no artifact can be encrypted"
        ) from exc
    if len(key) != 32:
        raise SetupRequired(f"{KEY_ENV} must decode to 32 bytes (AES-256)")
    return key


class ArtifactStore:
    def __init__(self, audit: AuditLog, key: bytes | None = None) -> None:
        self._lock = threading.RLock()
        self._audit = audit
        self._by_id: dict[str, Artifact] = {}
        self._key = key
        self._key_source = "injected" if key is not None else None
        self._key_error: str | None = None

    def key_status(self) -> dict:
        raw = os.environ.get(KEY_ENV)
        if self._key is not None:
            source = self._key_source or "injected"
            ready = True
            error = None
        elif raw:
            source = "environment"
            ready = False
            error = self._key_error
            try:
                _decode_key(raw)
                ready = True
            except SetupRequired as exc:
                error = exc.reason
                self._key_error = error
        else:
            source = "ephemeral"
            ready = True
            error = None
        return {
            "algorithm": ALGORITHM,
            "key_source": source,
            "ready": ready,
            "error": error,
        }

    def _ensure_key(self) -> bytes:
        if self._key is not None:
            return self._key
        raw = os.environ.get(KEY_ENV)
        if raw:
            try:
                self._key = _decode_key(raw)
            except SetupRequired as exc:
                self._key_error = exc.reason
                raise
            self._key_source = "environment"
            return self._key
        self._key = os.urandom(32)
        self._key_source = "ephemeral"
        return self._key

    def capture(
        self,
        *,
        tenant_id: str,
        session_id: str,
        kind: ArtifactKind,
        secret: str,
        label: str,
        retention_hours: int,
        actor: str = "system",
        correlation_id: str = "",
    ) -> Artifact:
        if not secret:
            raise LabError("captured value is empty")
        key = self._ensure_key()
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, secret.encode("utf-8"), None)
        captured_at = now_iso()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=retention_hours)
        ).isoformat()
        artifact = Artifact(
            artifact_id=f"art-{uuid.uuid4().hex[:10]}",
            tenant_id=tenant_id,
            session_id=session_id,
            kind=kind,
            label=label or kind.value,
            ciphertext=ciphertext,
            nonce=nonce,
            sha256=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
            redacted_preview=f"{label or kind.value} ••••",
            captured_at=captured_at,
            expires_at=expires_at,
        )
        with self._lock:
            self._by_id[artifact.artifact_id] = artifact
        self._audit.append(
            tenant_id=tenant_id,
            actor=actor,
            action="artifact.captured",
            object_type="artifact",
            object_id=artifact.artifact_id,
            correlation_id=correlation_id,
            detail={
                "session_id": session_id,
                "kind": kind.value,
                "cipher": ALGORITHM,
                "expires_at": expires_at,
            },
        )
        return artifact

    def get(self, artifact_id: str, *, tenant_id: str) -> Artifact:
        with self._lock:
            artifact = self._by_id.get(artifact_id)
        if artifact is None or artifact.tenant_id != tenant_id:
            raise LabNotFound("artifact not found")
        return artifact

    def for_session(self, session_id: str, *, tenant_id: str) -> list[Artifact]:
        with self._lock:
            return [
                artifact
                for artifact in self._by_id.values()
                if artifact.session_id == session_id and artifact.tenant_id == tenant_id
            ]

    def view(
        self,
        artifact_id: str,
        *,
        tenant_id: str,
        actor: str,
        correlation_id: str = "",
    ) -> dict:
        artifact = self.get(artifact_id, tenant_id=tenant_id)
        with self._lock:
            artifact.access_count += 1
        self._audit.append(
            tenant_id=tenant_id,
            actor=actor,
            action="artifact.accessed",
            object_type="artifact",
            object_id=artifact_id,
            correlation_id=correlation_id,
            detail={"session_id": artifact.session_id, "kind": artifact.kind.value},
        )
        return artifact.as_dict()

    def reveal(self, artifact_id: str, *, tenant_id: str, actor: str, purpose: str) -> str:
        """Decrypt for retention verification. Not routed; every call is audited."""
        artifact = self.get(artifact_id, tenant_id=tenant_id)
        if not artifact.available:
            raise LabError("artifact is no longer available; retention removed the ciphertext")
        key = self._ensure_key()
        self._audit.append(
            tenant_id=tenant_id,
            actor=actor,
            action="artifact.revealed",
            object_type="artifact",
            object_id=artifact_id,
            detail={"purpose": purpose},
        )
        return AESGCM(key).decrypt(artifact.nonce, artifact.ciphertext, None).decode("utf-8")

    def purge_expired(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        purged = 0
        with self._lock:
            for artifact in self._by_id.values():
                if not artifact.available:
                    continue
                expires = datetime.fromisoformat(artifact.expires_at)
                if expires <= current:
                    artifact.ciphertext = b""
                    artifact.nonce = b""
                    artifact.available = False
                    artifact.purged_at = now_iso()
                    purged += 1
        if purged:
            self._audit.append(
                tenant_id="system",
                actor="system",
                action="artifact.expired",
                object_type="artifact",
                object_id="retention-sweep",
                detail={"purged": purged, "counts_preserved": True},
            )
        return purged
