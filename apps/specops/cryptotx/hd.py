"""BIP39/BIP32 key derivation for the three chains the fabric signs.

Derivation is deterministic and library-backed: ``embit`` for the seed tree and
Bitcoin addresses, ``eth-account`` for Ethereum, ``tronpy`` for TRON. Nothing
here invents a curve or an address format.

The mnemonic never leaves the vault's decrypted buffer; these functions take a
seed and return a private-key byte string to the adapter that is about to sign.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from embit import bip32, bip39, ec, script
from embit.networks import NETWORKS

from specops.cryptotx.errors import ChainError
from specops.cryptotx.models import Chain, Network

#: Account-level path for each chain, as defined by SLIP-0044 coin types.
#: The final ``/0/{index}`` is the external chain and address index.
PURPOSE_PATHS: dict[Chain, str] = {
    Chain.ETHEREUM: "m/44h/60h/0h/0",
    Chain.TRON: "m/44h/195h/0h/0",
    Chain.BITCOIN: "m/84h/0h/0h/0",
}

_BTC_NETWORKS = {Network.MAINNET: NETWORKS["main"], Network.TESTNET: NETWORKS["test"]}


def new_mnemonic(words: int = 12) -> str:
    if words not in {12, 15, 18, 21, 24}:
        raise ValueError("word count must be one of 12, 15, 18, 21, 24")
    entropy_bytes = words * 4 // 3
    return bip39.mnemonic_from_bytes(secrets.token_bytes(entropy_bytes))


def validate_mnemonic(mnemonic: str) -> None:
    if not bip39.mnemonic_is_valid(mnemonic.strip()):
        raise ChainError("the supplied recovery phrase is not a valid BIP39 mnemonic")


def seed_from_mnemonic(mnemonic: str, passphrase: str = "") -> bytes:
    validate_mnemonic(mnemonic)
    return bip39.mnemonic_to_seed(mnemonic.strip(), passphrase)


@dataclass(frozen=True)
class DerivedKey:
    chain: Chain
    network: Network
    index: int
    path: str
    private_key: bytes = field(repr=False)
    public_key: bytes
    address: str


def account_path(chain: Chain, index: int) -> str:
    if index < 0 or index > 2**31 - 1:
        raise ValueError("derive index out of range")
    return f"{PURPOSE_PATHS[chain]}/{index}"


def _btc_address(pubkey: bytes, network: Network) -> str:
    return script.p2wpkh(ec.PublicKey.parse(pubkey)).address(_BTC_NETWORKS[network])


def derive_key(seed: bytes, chain: Chain, network: Network, index: int = 0) -> DerivedKey:
    path = account_path(chain, index)
    try:
        root = bip32.HDKey.from_seed(seed)
        node = root.derive(path)
    except Exception as exc:  # noqa: BLE001 - library refusal is the boundary
        raise ChainError(f"could not derive {chain.value} key at {path}") from exc
    private_key = node.key.serialize()
    public_key = node.key.get_public_key().serialize()
    if chain is Chain.ETHEREUM:
        from eth_account import Account

        address = Account.from_key(private_key).address
    elif chain is Chain.TRON:
        from tronpy.keys import PrivateKey

        address = PrivateKey(private_key).public_key.to_base58check_address()
    elif chain is Chain.BITCOIN:
        address = _btc_address(public_key, network)
    else:  # pragma: no cover - enum is exhaustive today
        raise ChainError(f"no derivation for {chain}")
    return DerivedKey(
        chain=chain,
        network=network,
        index=index,
        path=path,
        private_key=private_key,
        public_key=public_key,
        address=address,
    )
