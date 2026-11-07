"""Crypto transaction fabric API for the CI/SpecOps department.

The HTTP surface is a thin view over the package in ``apps/specops/cryptotx``:
the vault stays encrypted on disk, plan validation and execution live in the
executor, and this router only unlocks, stores, runs and reports.

Live money movement is not an HTTP toggle. ``POST /runs`` with
``dry_run: false`` still needs a valid approval token minted for the stored
plan digest, and the executor re-checks mainnet opt-in, policy caps and the
allowlist after this router returns. The approval endpoint exists so the
operator can mint that token after reviewing the plan; it is audited and never
returns the secret.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, resolve_tenant

try:
    from specops.cryptotx.approvals import mint_approval_token
    from specops.cryptotx.config import get_config
    from specops.cryptotx.errors import (
        ApprovalRequired,
        ChainError,
        CryptoTxError,
        PlanError,
        PolicyError,
        StoreError,
        VaultError,
        WalletNotFound,
    )
    from specops.cryptotx.executor import Executor
    from specops.cryptotx.models import Chain, Network, TransactionTree
    from specops.cryptotx.store import Store
    from specops.cryptotx.vault import create_vault, unlock_vault
except Exception:  # noqa: BLE001 - import boundary; report 503, do not fail boot
    mint_approval_token = None  # type: ignore[assignment]
    get_config = None  # type: ignore[assignment]
    ApprovalRequired = ChainError = CryptoTxError = PlanError = Exception  # type: ignore[assignment,misc]
    PolicyError = StoreError = VaultError = WalletNotFound = Exception  # type: ignore[assignment,misc]
    Executor = Store = None  # type: ignore[assignment,misc]
    Chain = Network = TransactionTree = None  # type: ignore[assignment,misc]
    create_vault = unlock_vault = None  # type: ignore[assignment,misc]

router = APIRouter(prefix="/specops/cryptotx", tags=["specops-cryptotx"])

_TENANT = Annotated[TenantContext, Depends(resolve_tenant)]


def _require() -> None:
    if Store is None or Executor is None or get_config is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="cryptotx integration unavailable")


def _status_for(exc: Exception) -> int:
    if isinstance(exc, WalletNotFound):
        return 404
    if isinstance(exc, (ApprovalRequired, PolicyError)):
        return 409
    if isinstance(exc, PlanError):
        return 422
    if isinstance(exc, VaultError):
        return 400
    if isinstance(exc, StoreError):
        return 503
    if isinstance(exc, ChainError):
        return 424
    return 400


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, CryptoTxError):
        return HTTPException(status_code=_status_for(exc), detail=exc.to_wire())
    return HTTPException(status_code=400, detail=str(exc))


class VaultCreate(BaseModel):
    password: str = Field(min_length=12)
    mnemonic: str | None = None
    words: int = 12
    overwrite: bool = False


class PasswordBody(BaseModel):
    password: str = Field(min_length=1)


class WalletCreate(PasswordBody):
    chain: str
    network: str = "testnet"
    label: str = ""
    account_index: int | None = None


class RunBody(PasswordBody):
    dry_run: bool | None = None
    approval_token: str | None = None


class ApprovalBody(BaseModel):
    plan_id: str
    ttl_s: int = Field(default=900, ge=1, le=86_400)


class PlanBody(BaseModel):
    plan: dict[str, Any]


@router.get("/status")
def cryptotx_status(ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    store = Store(get_config().state_path)
    return {
        "readiness": get_config().readiness(),
        "ledger": store.stats(),
        "served": ["/specops/cryptotx"],
        "missing": [],
        "scope": "tenant-wide",
    }


@router.post("/vault")
def create_cryptotx_vault(body: VaultCreate, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    cfg = get_config()
    if cfg.vault_path.exists() and not body.overwrite:
        raise HTTPException(status_code=409, detail="vault already exists")
    try:
        vault = create_vault(
            cfg.vault_path,
            body.password,
            mnemonic=body.mnemonic,
            words=body.words,
            overwrite=body.overwrite,
        )
    except (VaultError, ValueError) as exc:
        raise _fail(exc) from exc
    Store(cfg.state_path).audit(
        ctx.user_id if ctx else "operator", "vault_created", detail={}
    )
    view = vault.public_view()
    view["recovery_phrase"] = vault.payload.get("mnemonic")
    view["note"] = "store the recovery phrase offline; it is not returned again"
    return view


@router.post("/vault/unlock")
def unlock_cryptotx_vault(body: PasswordBody, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    try:
        vault = unlock_vault(get_config().vault_path, body.password)
    except VaultError as exc:
        raise _fail(exc) from exc
    return vault.public_view()


@router.post("/wallets")
def create_cryptotx_wallet(body: WalletCreate, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    try:
        chain = Chain(body.chain)
        network = Network(body.network)
        vault = unlock_vault(get_config().vault_path, body.password)
        wallet = vault.add_wallet(
            chain,
            network,
            body.label,
            account_index=body.account_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VaultError as exc:
        raise _fail(exc) from exc
    Store(get_config().state_path).audit(
        ctx.user_id if ctx else "operator",
        "wallet_created",
        detail={"wallet_id": wallet.wallet_id, "chain": wallet.chain.value,
                "network": wallet.network.value},
    )
    return wallet.to_dict()


@router.post("/wallets/list")
def list_cryptotx_wallets(body: PasswordBody, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    try:
        vault = unlock_vault(get_config().vault_path, body.password)
    except VaultError as exc:
        raise _fail(exc) from exc
    return vault.public_view()


@router.post("/plans")
def create_cryptotx_plan(body: PlanBody, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    try:
        plan = TransactionTree.from_dict(body.plan)
        plan.validate()
        store = Store(get_config().state_path)
        store.save_plan(plan)
    except (PlanError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StoreError as exc:
        raise _fail(exc) from exc
    return {"plan": plan.to_dict(), "digest": plan.digest()}


@router.get("/plans")
def list_cryptotx_plans(limit: int = 50, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    return {"plans": Store(get_config().state_path).list_plans(limit=limit)}


@router.get("/plans/{plan_id}")
def get_cryptotx_plan(plan_id: str, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    try:
        plan = Store(get_config().state_path).get_plan(plan_id)
    except StoreError as exc:
        raise _fail(exc) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    return {"plan": plan.to_dict(), "digest": plan.digest()}


@router.post("/approvals")
def mint_cryptotx_approval(body: ApprovalBody, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    cfg = get_config()
    try:
        plan = Store(cfg.state_path).get_plan(body.plan_id)
    except StoreError as exc:
        raise _fail(exc) from exc
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found")
    try:
        token = mint_approval_token(plan.digest(), cfg.approval_secret, ttl_s=body.ttl_s)
    except CryptoTxError as exc:
        raise _fail(exc) from exc
    expiry = int(token.split(".")[1])
    Store(cfg.state_path).audit(
        ctx.user_id if ctx else "operator",
        "approval_minted",
        plan_id=plan.plan_id,
        detail={"digest": plan.digest(), "expiry": expiry},
    )
    return {"plan_id": plan.plan_id, "digest": plan.digest(), "expiry": expiry,
            "token": token}


@router.post("/plans/{plan_id}/runs")
def run_cryptotx_plan(
    plan_id: str, body: RunBody, ctx: _TENANT = None
) -> dict[str, Any]:
    _require()
    cfg = get_config()
    try:
        store = Store(cfg.state_path)
        plan = store.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="plan not found")
        executor = Executor(config=cfg, store=store)
        result = executor.run(
            plan,
            password=body.password,
            dry_run=body.dry_run,
            approval_token=body.approval_token,
            actor=ctx.user_id if ctx else "operator",
        )
    except HTTPException:
        raise
    except CryptoTxError as exc:
        raise _fail(exc) from exc
    return result.to_dict()


@router.get("/runs")
def list_cryptotx_runs(
    plan_id: str | None = None, limit: int = 50, ctx: _TENANT = None
) -> dict[str, Any]:
    _require()
    return {
        "runs": Store(get_config().state_path).list_runs(
            plan_id=plan_id, limit=limit
        )
    }


@router.get("/runs/{run_id}")
def get_cryptotx_run(run_id: str, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    try:
        run = Store(get_config().state_path).get_run(run_id)
    except StoreError as exc:
        raise _fail(exc) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/audit")
def cryptotx_audit(limit: int = 100, ctx: _TENANT = None) -> dict[str, Any]:
    _require()
    return {"events": Store(get_config().state_path).audit_events(limit=limit)}
