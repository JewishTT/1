# 10_blockchain — public on-chain evidence

This family is read-only. It collects public chain records as source-bound evidence; it
does not manage signing keys, construct or sign transactions, broadcast payments, or move
assets between addresses or chains.

## Current coverage

| Chain | Provider | Source definitions |
|---|---|---|
| Bitcoin mainnet | Blockchain.com | Address summary and transaction lookup |
| Bitcoin mainnet | Blockstream Esplora | Address transaction feed and transaction detail |
| Bitcoin mainnet | mempool.space | Block-tip metadata |
| Ethereum mainnet | Ethplorer | Existing address/token metadata |
| Ethereum mainnet | Blockscout API v2 | Address metadata and recent transaction page |
| TRON mainnet | TronGrid v1 | Account metadata and recent transaction page |

Every endpoint is declared in YAML and passes through the common source catalogue and
HTTP executor. Raw response bytes, content digest, status, source identity and observation
provenance are retained by the canonical acquisition path. API credentials are resolved
from named environment variables and redacted from persisted request/redirect URLs.

## Pagination

- Blockstream's address endpoint returns a recent-transaction window. A transaction detail
  lookup is a separate pivot and may be used to inspect explicit input references.
- Blockscout v2 returns opaque `next_page_params`; this source currently captures its first
  page only. It does not invent a cursor or treat a page token as an integer offset.
- TronGrid v1 accepts a bounded page size. Current definitions intentionally capture the
  first 50 records; deeper traversal should be introduced only with a provider-specific
  cursor contract and a source-level ceiling.

## Transaction DAG semantics

The interpretation layer's `transaction_lineage.py` builds a deterministic dependency DAG
only from explicit parent transaction references. Bitcoin input transaction IDs can support
parent → spend edges. ETH/TRON transaction ordering, matching amounts, common addresses,
timestamps, bridge labels or proximity do not establish a dependency edge. Cross-chain
relations remain unresolved unless a source explicitly identifies the bridge event and its
evidence. Missing parents, duplicate hashes with conflicting raw digests, cross-network
references and cycles remain visible quality conditions.

## Verification

- Unit tests validate all source definitions, key substitution/redaction, pagination and DAG
  invariants.
- `apps/acquisition/_prove_blockchain_sources.py` is a strict live proof. It runs the six
  definitions through `SourceConnector`, parses their captured bytes through the declared
  parser family, and fails on HTTP errors, empty results or unresolved required fields.
- GitHub Actions runs that proof in `.github/workflows/blockchain-source-live-proof.yml`.
  A live run is required before these endpoints should be called production-verified.
