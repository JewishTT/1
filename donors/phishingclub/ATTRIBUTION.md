# Attribution — Phishing Club

This directory contains a vendored checkout of **Phishing Club** (`donors/phishingclub`).

- **Project**: Phishing Club — phishing simulation, training and red-team phishing framework
- **Copyright**: Copyright (C) 2025-present Phishing Club
- **Licence**: GNU Affero General Public License, version 3 (AGPL-3.0). The full text is
  in `LICENSE`; the project notice, including its dual-licensing statement, is in
  `NOTICE`; the copyright statement is in `COPYRIGHT`.
- **Source**: the upstream project is identified in `README.md`
  (<https://github.com/phishingclub/phishingclub>).
- **Changes**: the platform does not modify the vendored tree. The platform re-expresses
  the donor's engagement taxonomy in `apps/specops/engagement/` and does not embed the
  donor frontend or palette.

## Source-offer obligation

Phishing Club is used under AGPL-3.0 for internal lab work. Anyone who operates a
modified version as a network service, or distributes a covered work, must offer the
corresponding source under AGPL-3.0 §13. This checkout is the source for the vendored
tree; modifications made by the platform, if any, are recorded in the repository history
and must be offered under the same terms. Contact: `license@phishing.club` for the
donor's commercial-licensing option; the platform does not rely on that option.

## Review status

A licence signature match is **not** a licence review. As of 2026-11-01:

- the `LICENSE` file matches the AGPL-3.0 SPDX signature (sha256 prefix
  `fb5e472602401866`);
- the checkout carries no upstream revision/tag in `donors/registry.yaml`;
- a human has not confirmed that the licence governs every bundled asset and third-party
  component;
- therefore the registry entry remains `status: unverified` and the donor adapter
  remains disabled.

The platform's Red-Team Lab runs its own lab engine while this block stands. Enabling the
donor requires a verified registry entry, a pinned upstream revision, this attribution,
and the source-offer route above.

## No warranty

The donor is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the AGPL-3.0 text in `LICENSE`.

## Use restriction recorded by the platform

This checkout is used only inside the isolated SpecOps Red-Team Lab defined by
`docs/adr/ADR-0040-lab-only-red-team-exception.md`. It is not used against production
targets, real personal data, real credentials or unauthorized brand assets, and it is
not offered as a public network service by this platform.
