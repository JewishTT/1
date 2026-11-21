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

## Preserved integration snapshot

To make the legacy department recoverable as a whole, a source mirror is also retained
under mirror/ with the former control-plane SpecOps routers and catalog service,
React CI/SpecOps, Lab and GhostLine surfaces, their component tests, screenshot
harness, isolated lab compose file, donor dossier, and feature specifications for
CI/SpecOps (027) and the Phishing Club lab (036).

These mirrored integration files are historical copies. The corresponding active
routes and UI files remain mounted at their original paths until the new consumer
services have been wired and verified end-to-end. The feature 031 GhostLine spec
remains in its source location because the repository connector did not allow that
archive copy in this change; its live UI and route sources are mirrored under
mirror/apps/ as listed by the platform source inventory.
