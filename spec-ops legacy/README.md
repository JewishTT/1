# SpecOps legacy archive

This directory preserves the former SpecOps application package as a source archive.
The complete 68-file tree formerly rooted at `apps/specops/` is retained under
`apps/specops/`, including its RoE gate, red-team lab, emulation, phishing,
counterintelligence, forensics, social projection, engagement fabric, GhostLine,
cryptotx modules, and original package tests.

## Runtime transition

- The active `apps/specops/__init__.py` is a temporary import bridge to the archived
  package. It exists only so the still-mounted control-plane adapters can be migrated
  without making this archive a production dependency by accident.
- New SpecOps&CI domain work belongs in `apps/specops_ci/`.
- Recon, collection, discovery and entity resolution belong to the foundational
  Intelligence Silo. New domain consumers must use
  `shared.contracts.intelligence_feed.IntelligenceReadPort`.
- The existing API route wrappers, webapp canvases, feature specifications and donor
  dossiers remain in their established paths for the migration period. They are not
  represented as having been relocated by this source-package archive.

Do not extend the archived package. New functionality requires a migration task,
an explicit Intelligence consumer contract, and tests proving tenant and authorization
boundaries. Remove the compatibility bridge only after all API adapters and callers
have moved and the legacy import tests have been retired or relocated.
