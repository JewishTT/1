# On-chain evidence collection and transaction lineage

## Scope

SpecOps uses public-chain data as investigation evidence. Acquisition is read-only and uses
the existing source catalogue, HTTP executor, capture/observation path and parser-family
contracts. It does not generate or custody wallet secrets, sign or broadcast transactions,
route assets, or execute cross-chain swaps.

## Source coverage

- **Bitcoin:** Blockchain.com, Blockstream Esplora and mempool.space. The catalogue includes
  address summary, transaction lookup, address transaction feed and block-tip metadata.
- **Ethereum mainnet:** the existing Ethplorer integration plus Blockscout API v2 address
  and transaction records.
- **TRON mainnet:** TronGrid v1 account and transaction records.

Provider credentials, where required, are named by environment variable, injected only into
the outbound request and redacted from persisted URL provenance and transport failures.
All feeds retain the raw response bytes and SHA-256 content digest.

## Evidence-only transaction DAG

`apps/interpretation/transaction_lineage.py` projects immutable transaction observations
into a deterministic DAG. Nodes are keyed by (chain, network, transaction id). Edges are
parent transaction → spending transaction and are admitted only from explicit source fields
such as Bitcoin `vin[].txid`.

The projector does not infer dependencies from timing, value, address overlap or graph
proximity. It does not treat ETH/TRON account sequence as a parent transaction reference.
Cross-chain edges require an explicit source-backed bridge/event reference and are not
manufactured by a heuristic correlation.

The result retains:
- all supporting observation IDs and raw-record digests for each transaction;
- missing parent references;
- conflicting observations for a transaction ID;
- cross-chain/cross-network references that were refused;
- cycle members and a deterministic topological order for acyclic components.

An incomplete DAG is still returned with its defects named; the projector never silently
repairs or discards evidence.

## Live acceptance

The strict live proof `apps/acquisition/_prove_blockchain_sources.py` fetches one real
page per source via `SourceConnector`, parses the captured raw bytes with the declared
source parser and requires HTTP 200 plus at least one usable record and no unresolved
required fields. GitHub Actions runs it separately from offline unit tests so provider
availability is not confused with a hermetic contract pass.
