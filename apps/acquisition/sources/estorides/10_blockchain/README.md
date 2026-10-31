# 10_blockchain — public on-chain evidence

This family is read-only. It collects public chain records as source-bound evidence; it
does not manage wallet secrets, sign or broadcast transactions, route assets, or execute
cross-chain swaps.

## Current catalogue coverage

| Chain | Provider | Source definitions | Credential |
|---|---|---|---|
| Bitcoin mainnet | Blockchain.com | Existing address summary and transaction lookup | Provider policy |
| Bitcoin mainnet | Blockstream Esplora | Address transaction feed and transaction detail | Public endpoint |
| Bitcoin mainnet | mempool.space | Existing block-tip metadata | Public endpoint |
| Ethereum mainnet | Ethplorer | Existing address/token metadata | `ETHPLORER_API_KEY` |
| Ethereum mainnet | Blockscout API v2 | Address metadata and recent transaction page | Public endpoint |
| TRON mainnet | TronGrid v1 | Account metadata and recent transaction page | `TRONGRID_API_KEY` |

The six source definitions added or promoted in this vertical slice are validated through the
same YAML catalogue and HTTP executor as every other source. Provider responses are captured
raw-first; content digests, source identity, HTTP status and capture provenance travel through
the acquisition path. Credential values are injected only into outbound requests and redacted
from persisted URL provenance and transport exception details.

TRON definitions deliberately fail closed when `TRONGRID_API_KEY` is absent. Supply it as
a repository/environment secret to enable the authenticated TRON live proof. A missing key
is not interpreted as an empty account or a successful no-result response.

## Pagination and coverage boundaries

- Blockstream's address endpoint returns its recent transaction window. Transaction detail is
  a separate pivot and carries the explicit UTXO input references used by lineage.
- Blockscout v2 returns opaque `next_page_params`; the current definition captures the first
  page only. The executor does not convert an opaque provider cursor to a page number.
- TronGrid account transactions are deliberately bounded to the first 50 confirmed records.
  A deeper walk requires a provider-specific cursor contract and a source-level ceiling.
- The live blockchain workflow queries and parses one page per source. It reports missing
  credentials and provider failures per source rather than manufacturing records.

## Transaction DAG semantics

The interpretation layer's `transaction_lineage.py` builds a deterministic dependency DAG
only from explicit parent transaction references. Bitcoin input transaction IDs support
parent → spending-transaction edges. ETH/TRON account ordering, matching amounts, shared
addresses, timestamps, bridge labels or proximity do not establish a dependency edge.
Cross-chain relationships remain unresolved unless a source explicitly identifies a
bridge/event and its evidence.

Nodes preserve all supporting observation IDs and raw-record digests. Missing parents,
conflicting observations for a transaction ID, cross-chain/cross-network references and
cycle members remain explicit quality conditions. The cycle detector reports strongly
connected cycle members, not unrelated descendants that happen to be blocked behind a cycle.
A partial graph is returned with its defects; evidence is not silently repaired or discarded.

## Verification

- Offline contracts validate all source declarations, required credentials, parser paths,
  bounded pagination, URL redaction and transaction-lineage invariants.
- `apps/acquisition/_prove_blockchain_sources.py` fetches through `SourceConnector` and
  parses the captured bytes through each source's declared parser. The GitHub Actions run
  requires usable records from all six sources; TRON requires the operator secret above.
- `apps/acquisition/_prove_commoncrawl.py` has a separate live proof that checks a live CDX
  index row and a real HTTP 206 WARC byte-range response, then parses the matching WARC
  payload. It passed on 2026-10-31.
- `apps/acquisition/_prove_airbyte.py` obtains SPEC and DISCOVER from the pinned real
  connector, writes a restrictive temporary config and catalog, then performs the existing
  raw capture → Observation → Redpanda → consumer read-back proof.
- Live Airbyte/SearXNG stack acceptance is run separately from hermetic unit tests, so a
  provider/registry outage is not confused with an offline contract result.
