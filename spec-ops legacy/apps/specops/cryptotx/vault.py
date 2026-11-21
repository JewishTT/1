"""Encrypted, file-backed HD wallet vault.

The vault holds one BIP39 mnemonic and any number of public wallet records
derived from it. At rest the whole payload is encrypted with AES-256-GCM under
a scrypt-derived key; the KDF parameters travel with the file so an older vault
still opens after the default cost is raised.

The password is never written anywhere, never placed in an exception and never
returned by an accessor. Decrypted key material exists only for the duration of
a signing operation.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from specops.cryptotx import hd
from specops.cryptotx.errors import VaultError, WalletNotFound
from specops.cryptotx.models import Chain, Network, Wallet, now_iso

_FILE_VERSION = 1
_AAD = b"cognitive-cryptotx-vault-v1"
_MIN_PASSWORD = 12
_DEFAULT_SCRYPT_N = 2**15
_SALT_BYTES = 16
_NONCE_BYTES = 12


def _scrypt_n() -> int:
    raw = os.environ.get("CRYPTOTX_SCRYPT_N")
    if not raw:
        return _DEFAULT_SCRYPT_N
    value = int(raw)
    if value < 2**12 or value > 2**20 or value & (value - 1):
        raise ValueError("CRYPTOTX_SCRYPT_N must be a power of two between 2**12 and 2**20")
    return value


def _derive_key(password: str, salt: bytes, n: int, r: int = 8, p: int = 1) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=n, r=r, p=p)
    return kdf.derive(password.encode("utf-8"))


def _encode(payload: dict[str, Any], key: bytes) -> dict[str, Any]:
    nonce = secrets.token_bytes(_NONCE_BYTES)
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _AAD)
    return {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def _atomic_write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".tmp-{secrets.token_hex(4)}")
    data = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(temp, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


@dataclass
class _Envelope:
    kdf: dict[str, Any]
    cipher: dict[str, str]


def _read_envelope(path: Path) -> tuple[_Envelope, dict[str, Any]]:
    if not path.exists():
        raise VaultError(f"vault does not exist: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VaultError(f"vault is unreadable: {path}") from exc
    if document.get("version") != _FILE_VERSION:
        raise VaultError("unsupported vault version")
    try:
        envelope = _Envelope(kdf=document["kdf"], cipher=document["cipher"])
    except KeyError as exc:
        raise VaultError("vault is missing its KDF or cipher block") from exc
    return envelope, document


@dataclass
class UnlockedVault:
    """An in-memory view of a decrypted vault. ``repr`` names nothing secret."""

    path: Path
    key: bytes
    kdf: dict[str, Any]
    payload: dict[str, Any]

    def __repr__(self) -> str:
        return f"UnlockedVault(path={self.path!s}, wallets={len(self.wallets())})"

    def wallets(self) -> list[Wallet]:
        return [Wallet.from_dict(item) for item in self.payload.get("wallets", [])]

    def wallet(self, wallet_id: str) -> Wallet:
        for wallet in self.wallets():
            if wallet.wallet_id == wallet_id:
                return wallet
        raise WalletNotFound(f"no wallet with id {wallet_id!r}")

    def wallet_for(self, chain: Chain, network: Network, label: str | None = None) -> Wallet | None:
        for wallet in self.wallets():
            if wallet.chain is chain and wallet.network is network:
                if label is None or wallet.label == label:
                    return wallet
        return None

    def add_wallet(
        self,
        chain: Chain,
        network: Network,
        label: str,
        *,
        account_index: int | None = None,
    ) -> Wallet:
        seed = self._seed()
        existing = self.wallets()
        if account_index is None:
            account_index = max(
                (
                    w.account_index
                    for w in existing
                    if w.chain is chain and w.network is network
                ),
                default=-1,
            ) + 1
        derived = hd.derive_key(seed, chain, network, account_index)
        for wallet in existing:
            if wallet.address.lower() == derived.address.lower():
                raise VaultError("that address is already present in the vault")
        wallet = Wallet(
            wallet_id=f"w-{chain.value[:2]}-{secrets.token_hex(6)}",
            label=label or f"{chain.value}-{network.value}-{account_index}",
            chain=chain,
            network=network,
            address=derived.address,
            derivation_path=derived.path,
            account_index=account_index,
            created_at=now_iso(),
        )
        self.payload.setdefault("wallets", []).append(wallet.to_dict())
        self.save()
        return wallet

    def private_key(self, wallet_id: str) -> hd.DerivedKey:
        wallet = self.wallet(wallet_id)
        return hd.derive_key(self._seed(), wallet.chain, wallet.network, wallet.account_index)

    def public_view(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "wallet_count": len(self.payload.get("wallets", [])),
            "wallets": [wallet.to_dict() for wallet in self.wallets()],
        }

    def save(self) -> None:
        _envelope, document = _read_envelope(self.path)
        document["cipher"] = _encode(self.payload, self.key)
        _atomic_write(self.path, document)

    def _seed(self) -> bytes:
        mnemonic = self.payload.get("mnemonic")
        if not mnemonic:
            raise VaultError("vault has no mnemonic")
        return hd.seed_from_mnemonic(mnemonic, str(self.payload.get("passphrase", "")))


def create_vault(
    path: Path | str,
    password: str,
    *,
    mnemonic: str | None = None,
    passphrase: str = "",
    words: int = 12,
    overwrite: bool = False,
) -> UnlockedVault:
    if len(password) < _MIN_PASSWORD:
        raise VaultError(f"vault password must be at least {_MIN_PASSWORD} characters")
    target = Path(path)
    if target.exists() and not overwrite:
        raise VaultError(f"refusing to overwrite existing vault: {target}")
    mnemonic = mnemonic or hd.new_mnemonic(words)
    hd.validate_mnemonic(mnemonic)
    salt = secrets.token_bytes(_SALT_BYTES)
    n = _scrypt_n()
    kdf = {"name": "scrypt", "n": n, "r": 8, "p": 1,
           "salt": base64.b64encode(salt).decode("ascii")}
    key = _derive_key(password, salt, n)
    payload = {
        "mnemonic": mnemonic.strip(),
        "passphrase": passphrase,
        "created_at": now_iso(),
        "wallets": [],
    }
    cipher = _encode(payload, key)
    document = {"version": _FILE_VERSION, "kdf": kdf, "cipher": cipher}
    _atomic_write(target, document)
    return UnlockedVault(path=target, key=key, kdf=kdf, payload=payload)


def unlock_vault(path: Path | str, password: str) -> UnlockedVault:
    target = Path(path)
    envelope, document = _read_envelope(target)
    kdf = envelope.kdf
    try:
        if kdf.get("name") != "scrypt":
            raise VaultError("unsupported KDF")
        salt = base64.b64decode(kdf["salt"])
        key = _derive_key(password, salt, int(kdf["n"]), int(kdf["r"]), int(kdf["p"]))
        nonce = base64.b64decode(envelope.cipher["nonce"])
        ciphertext = base64.b64decode(envelope.cipher["ciphertext"])
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, _AAD)
    except InvalidTag as exc:
        raise VaultError("vault password is incorrect") from exc
    except (KeyError, ValueError) as exc:
        raise VaultError("vault KDF or cipher block is malformed") from exc
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VaultError("vault plaintext is malformed") from exc
    return UnlockedVault(path=target, key=key, kdf=kdf, payload=payload)
