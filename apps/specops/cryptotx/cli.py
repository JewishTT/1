"""Operator CLI for the crypto transaction fabric.

Run from the repository root with ``apps`` on the module path, for example on
PowerShell::

    $env:PYTHONPATH="apps"; .venv\Scripts\python.exe -m specops.cryptotx.cli status

Passwords are read from ``CRYPTOTX_VAULT_PASSWORD`` or a no-echo prompt; they are never
accepted as a command-line argument, because process listings are world-readable
on most hosts. Approval tokens are printed only from ``mint-approval`` and are
bound to the stored plan digest.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from specops.cryptotx.approvals import mint_approval_token
from specops.cryptotx.config import get_config
from specops.cryptotx.errors import CryptoTxError
from specops.cryptotx.executor import Executor
from specops.cryptotx.models import Chain, Network, TransactionTree
from specops.cryptotx.store import Store
from specops.cryptotx.vault import create_vault, unlock_vault


def _password(confirm: bool = False) -> str:
    value = os.environ.get("CRYPTOTX_VAULT_PASSWORD")
    if value:
        return value
    first = getpass.getpass("vault password: ")
    if confirm and getpass.getpass("repeat password: ") != first:
        raise SystemExit("passwords differ")
    return first


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptotx", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="readiness, ledger counts and swap coverage")

    init = sub.add_parser("init-vault", help="create the encrypted vault")
    init.add_argument("--mnemonic")
    init.add_argument("--words", type=int, default=12)
    init.add_argument("--overwrite", action="store_true")

    add = sub.add_parser("add-wallet", help="derive and store one wallet address")
    add.add_argument("--chain", required=True, choices=[c.value for c in Chain])
    add.add_argument(
        "--network", default="testnet", choices=[n.value for n in Network]
    )
    add.add_argument("--label", default="")
    add.add_argument("--account-index", type=int)

    sub.add_parser("wallets", help="list public wallet records")

    plan = sub.add_parser("plan", help="validate and store a plan JSON file")
    plan.add_argument("file", type=Path)

    run = sub.add_parser("run", help="execute a stored plan")
    run.add_argument("plan_id")
    run.add_argument("--live", action="store_true", help="broadcast instead of dry-run")
    run.add_argument("--approval-token", default=os.environ.get("CRYPTOTX_APPROVAL_TOKEN"))
    run.add_argument("--actor", default="cli")

    mint = sub.add_parser("mint-approval", help="mint a digest-bound approval token")
    mint.add_argument("plan_id")
    mint.add_argument("--ttl", type=int, default=900)

    runs = sub.add_parser("runs", help="list runs")
    runs.add_argument("--plan-id")
    runs.add_argument("--limit", type=int, default=50)

    audit = sub.add_parser("audit", help="show recent audit events")
    audit.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = get_config()
    store = Store(cfg.state_path)
    try:
        if args.command == "status":
            _print({"readiness": cfg.readiness(), "ledger": store.stats()})
            return 0
        if args.command == "init-vault":
            if cfg.vault_path.exists() and not args.overwrite:
                raise SystemExit(f"vault already exists: {cfg.vault_path}")
            vault = create_vault(
                cfg.vault_path,
                _password(confirm=True),
                mnemonic=args.mnemonic,
                words=args.words,
                overwrite=args.overwrite,
            )
            view = vault.public_view()
            view["recovery_phrase"] = vault.payload.get("mnemonic")
            _print(view)
            return 0
        if args.command == "add-wallet":
            vault = unlock_vault(cfg.vault_path, _password())
            wallet = vault.add_wallet(
                Chain(args.chain),
                Network(args.network),
                args.label,
                account_index=args.account_index,
            )
            store.audit(
                "cli",
                "wallet_created",
                detail={"wallet_id": wallet.wallet_id, "chain": wallet.chain.value,
                        "network": wallet.network.value},
            )
            _print(wallet.to_dict())
            return 0
        if args.command == "wallets":
            _print(unlock_vault(cfg.vault_path, _password()).public_view())
            return 0
        if args.command == "plan":
            document = json.loads(Path(args.file).read_text(encoding="utf-8"))
            if isinstance(document, dict) and isinstance(document.get("plan"), dict):
                document = document["plan"]
            tree = TransactionTree.from_dict(document)
            tree.validate()
            store.save_plan(tree)
            store.audit("cli", "plan_stored", plan_id=tree.plan_id,
                        detail={"digest": tree.digest()})
            _print({"plan_id": tree.plan_id, "digest": tree.digest()})
            return 0
        if args.command == "run":
            plan = store.get_plan(args.plan_id)
            if plan is None:
                raise SystemExit(f"plan not found: {args.plan_id}")
            result = Executor(config=cfg, store=store).run(
                plan,
                password=_password(),
                dry_run=not args.live,
                approval_token=args.approval_token,
                actor=args.actor,
            )
            _print(result.to_dict())
            return 0
        if args.command == "mint-approval":
            plan = store.get_plan(args.plan_id)
            if plan is None:
                raise SystemExit(f"plan not found: {args.plan_id}")
            token = mint_approval_token(
                plan.digest(), cfg.approval_secret, ttl_s=args.ttl
            )
            store.audit(
                "cli",
                "approval_minted",
                plan_id=plan.plan_id,
                detail={"digest": plan.digest()},
            )
            _print({"plan_id": plan.plan_id, "digest": plan.digest(),
                    "token": token})
            return 0
        if args.command == "runs":
            _print({"runs": store.list_runs(plan_id=args.plan_id, limit=args.limit)})
            return 0
        if args.command == "audit":
            _print({"events": store.audit_events(limit=args.limit)})
            return 0
    except CryptoTxError as exc:
        print(json.dumps(exc.to_wire(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
