# LICENCE ANALYSIS — estorides donor integration

**Scope of this document.** Technical reading of licence text for engineering planning.

**This is not legal advice. I am not a lawyer.** Nothing below is a legal opinion, and no
engineer or agent is competent to substitute for one. Every claim about what a licence
permits or forbids is derived from quoting the licence text, and quoting is not
interpretation. Before **any** code, file, or specification derived from `donors/estorides/`
moves into this repository, a qualified human must confirm the reading in this document.
The purpose of this document is to make that human review fast and to prevent an agent from
making a relicensing decision by accident.

---

## 1. Measured facts

All facts below were read directly from disk. Citations are `file:line`.

### 1.1 The donor's licence file is AGPL-3.0

`donors/estorides/LICENSE:1-4`:

```
                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

  Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
  Everyone is permitted to copy and distribute verbatim copies
  of this license document, but changing it is not allowed.
```

This is a complete, unmodified, 661-line AGPL-3.0 text — not a fragment, not a reference to
another file. `donors/estorides/README.md:648` carries the matching badge:

```
[![License: AGPL v3](https://img.shields.io/badge/License-AGPLv3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
```

### 1.2 The donor's packaging metadata says GPL-3.0

`donors/estorides/pyproject.toml:10`:

```toml
license = {text = "GPL-3.0"}
```

`donors/estorides/pyproject.toml:14-24` reinforces it:

```toml
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Information Technology",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    ...
]
```

So the trove-style metadata string and the PyPI classifier both say GPLv3, while the
licence file and the README badge both say AGPLv3.

### 1.3 Which is authoritative, and what the disagreement costs

**The `LICENSE` file is authoritative.** The technical reason, from the licence's own
`LICENSE:139-140`:

> The Corresponding Source for a work in source code form is that
> same work.

The full 661-line terms that govern the code are the ones physically shipped with the code.
`pyproject.toml` `license = {text = "GPL-3.0"}` is a metadata *label* attached to a
distribution artefact; it is a string in a build config, not a grant of rights. No copyright
holder conveys rights by writing a label in a manifest. The only thing that grants rights
here is the AGPL-3.0 text the copyright holder actually applied to the source.

**The consequence of the disagreement is that the practical risk is asymmetric, and it
favours the more restrictive reading.** GPL-3.0 and AGPL-3.0 are near-identical in their
copyleft reach for *conveying*; they diverge almost entirely on the network clause, and
AGPL-3.0 is the strict superset. AGPL-3.0 §13 has no GPL-3.0 counterpart. Therefore:

- If the AGPL-3.0 reading is correct and we planned on GPL-3.0, we have **under-planned**:
  we omitted the network clause that AGPL adds on top of GPL.
- If the GPL-3.0 reading is correct and we plan on AGPL-3.0, we have **over-planned**:
  we will hand out source we did not have to hand out.

An engineer optimising for the "GPL-3.0" label is therefore optimising in exactly the
direction that removes the safety margin. The asymmetry is the whole practical content of
this disagreement.

**The disagreement is not harmless and should be escalated, not silently resolved.** It is
a defect in the donor's own release. It is on the record in two places that disagree. A
human should decide whether to (a) treat the repo as AGPL (the safe, and textually
supported, reading) and note the defect, or (b) open an upstream issue asking the copyright
holder to correct `pyproject.toml`, and wait for an authoritative statement. **This document
proceeds on reading (a) throughout.** Do not let an agent resolve this ambiguity on its own;
it is precisely the kind of decision that looks clerical and is actually load-bearing.

---

## 2. What AGPL-3.0 permits for private use that never conveys

Short answer: **yes — studying, reading, running, and privately adapting carry no
source-disclosure obligation, and acceptance of the licence is not even required to do them.**
But the permission is conditional in a way that matters, and one clause must be flagged
before you rely on it.

### 2.1 Reading and running

`LICENSE:146-150` (§2):

> This License explicitly affirms your unlimited
> permission to run the unmodified Program.  The output from running a
> covered work is covered by this License only if the output, given its
> content, constitutes a covered work.

`LICENSE:423-432` (§9):

> You are not required to accept this License in
> order to receive or
> run a copy of the Program.  Ancillary propagation of a covered work
> occurring solely as a consequence of using peer-to-peer transmission
> to receive a copy likewise does not require acceptance.  However,
> nothing other than this License grants you permission to propagate or
> modify any covered work.  These actions infringe copyright if you do
> not accept this License.  Therefore, by modifying or propagating a
> covered work, you indicate your acceptance of this License to do so.

So: **reading the source, studying it, and running it require no obligation and do not
even require you to accept the licence.** No `LICENSE` file must accompany your internal
reading. No source must be published. There is no attribution obligation triggered by
merely having read the file.

### 2.2 The clause that must be flagged: private modification is not "propagate", but it *is* acceptance

`LICENSE:80-85` (§0):

> To "propagate" a work means to do anything with it that, without
> permission, would make you directly or secondarily liable for
> infringement under applicable copyright law, except executing it on a
> computer or modifying a private copy.  Propagation includes copying,
> distribution (with or without modification), making available to the
> public, and in some countries other activities as well.

The parenthetical **"except executing it on a computer or modifying a private copy"** means
that adapting estorides code on a private machine, with no distribution, is not propagation
and so triggers none of the §4/§5/§6 conditions.

However — and this is the trap — `LICENSE:72-75` (§0) defines modification broadly:

> To "modify" a work means to copy from or adapt all or part of the work
> in a fashion requiring copyright permission, other than the making of an
> exact copy.  The resulting work is called a "modified version" of the
> earlier work or a work "based on" the earlier work.

and `LICENSE:167-216` (§5) attaches conditions to *conveying* a modified version, **not** to
modifying it privately. So a private adaptation imposes no disclosure duty — **but per §9 it
does constitute acceptance of the licence, and it creates a "modified version" that, once
conveyed, will drag in §5(c) for the entire work.** The private-adaptation safe harbour is
real, but it is a *delay* mechanism, not an *exemption*. The moment that adapted code is
conveyed, the §5(c) whole-work licence obligation attaches retroactively to the modified
version. It is a fuse, not a shield.

### 2.3 What "conveying" is *not*

`LICENSE:87-89` (§0):

> To "convey" a work means any kind of propagation that enables other
> parties to make or receive copies.  Mere interaction with a user through
> a computer network, with no transfer of a copy, is not conveying.

This single sentence is the hinge for option (c) in §5 below. Network use is not conveyance
*unless a copy moves*. Calling an API is not conveyance.

---

## 3. What triggers the copyleft obligation

There are exactly two triggers in AGPL-3.0 that matter here. Everything else is
housekeeping.

### 3.1 Trigger 1 — conveyance (§4, §5, §6)

**What counts as "conveying":** per `LICENSE:87-89` above, any propagation that **enables
other parties to make or receive copies**. Per `LICENSE:80-85`, propagation includes
"copying, distribution (with or without modification), making available to the public."

In engineering terms, for this repository: committing a copied file into the git tree and
pushing that tree to a remote that anyone else can read **is** conveyance. It is not
ambiguous. `origin` is `https://github.com/JewishTT/1.git` (§4.1 below), so a pushed commit
that contains a copied AGPL file is a conveyance to GitHub and its users.

**§4 — conveying verbatim copies** (`LICENSE:185-191`):

> You may convey verbatim copies of the Program's source code as you
> receive it, in any medium, provided that you
> conspicuously and
> appropriately publish on each copy an appropriate copyright notice;
> keep intact all notices stating that this License and any
> non-permissive terms added in accord with section 7 apply to the code;
> keep intact all notices of the absence of any warranty; and give all
> recipients a copy of this License along with the Program.

Note what §4 does **not** say: it does not say the whole of your work becomes AGPL. It says
you must carry the notices and pass along the licence. A verbatim copy in an otherwise
unrelated aggregate is a *disclosure* obligation, not a *relicensing* obligation.

**§5 — conveying modified source** (`LICENSE:198-216`):

> You may convey a work based on the Program, or the modifications to
> produce it from the Program, in the form of source code under the
> terms of section 4, provided that you also meet all of these conditions:
>
>     a) The work must carry prominent notices stating that you modified
>     it, and giving a relevant date.
>
>     b) The work must carry prominent notices stating that it is
>     released under this License and any conditions added under section
>     7.  This requirement modifies the requirement in section 4 to
>     "keep intact all notices".
>
>     c) You must license the entire work, as a whole, under this
>     License to anyone who comes into possession of a copy.  This
>     License will therefore apply, along with any applicable section 7
>     additional terms, to the whole of the work, and all its parts,
>     regardless of how they are packaged.  This License gives no
>     permission to license the work in any other way, but it does not
>     invalidate such permission if you have separately received it.
>
>     d) If the work has interactive user interfaces, each must display
>     Appropriate Legal Notices; however, if the Program has interactive
>     interfaces that do not display Appropriate Legal Notices, your
>     work need not make them do so.

**§5(c) is the clause that makes a combined work derivative.** Read the operative words:
"the entire work, as a whole ... to the whole of the work, and all its parts, **regardless of
how they are packaged**." It does not stop at the copied file. It does not stop at the
package. It does not stop at the directory. If you adapt estorides code and convey the
result, §5(c) reaches every part of what you conveyed, however you arranged it on disk.

And `LICENSE:163-165` (§2) closes the exit:

> Conveying under any other circumstances is permitted solely under
> the conditions stated below.  Sublicensing is not allowed; section 10
> makes it unnecessary.

So you cannot convey an AGPL-derived work and then relicense the whole thing under
something else. The only sublicensing relief is the GPLv3 compatibility paragraph at
`LICENSE:553-559`, which permits *combining* with GPLv3-licensed works — it does not permit
relicensing under MIT, Apache, or proprietary terms.

**The boundary of "combined work" — the aggregate clause** (`LICENSE:223-231`):

> A compilation of a covered work with other separate and independent
> works, which are not by their nature extensions of the covered work,
> and which are not combined with it such as to form a larger program,
> in or on a volume of a storage or distribution medium, is called an
> "aggregate" if the compilation and its resulting copyright are not
> used to limit the access or legal rights of the compilation's users
> beyond what the individual works permit.  Inclusion of a covered work
> in an aggregate does not cause this License to apply to the other
> parts of the aggregate.

This is the most important clause for §5 of this document (the `donors/` hazard). Read the
three conjunctive conditions: the other works must be (i) separate and independent, (ii) not
extensions *by their nature*, and (iii) not "combined with it such as to form a larger
program." Sitting on the same disk satisfies (i) and (ii). What breaks the aggregate is
(iii) — actual combination into a larger program, i.e. importing, linking, vendoring into a
build, or shipping together as one artifact.

### 3.2 Trigger 2 — remote network interaction (§13)

`LICENSE:540-551`:

> Notwithstanding any other provision of this License, if you modify the
> Program, your modified version must prominently offer all users
> interacting with it remotely through a computer network (if your version
> supports such interaction) an opportunity to receive the Corresponding
> Source of your version by providing access to the Corresponding Source
> from a network server at no charge, through some standard or customary
> means of facilitating copying of software.

**What counts as "remote network interaction":** the clause is conditioned on
`LICENSE:543-544` — "if you modify the Program, your modified version must prominently offer
all users **interacting with it** remotely through a computer network." The obligation runs
to the **operator of the modified program**, toward **its users**. It is not an obligation on
whoever happens to reach the program over the network. Combined with `LICENSE:87-89` ("Mere
interaction with a user through a computer network, with no transfer of a copy, is not
conveying"), the division of labour is clear:

- If **we** run a modified estorides and our users reach it over the network, **we** owe the
  source offer. This is a real and continuing obligation with no "did I distribute it?"
  escape — that is precisely the hole AGPL was written to close, as the preamble states at
  `LICENSE:38-48`.
- If we merely **call** somebody else's unmodified instance, the obligation is theirs and
  only if they modified it. We receive no copy, so we convey nothing and are owed nothing.

**The practical §13 exposure for this repository is therefore contingent on the
"modify + operate + remote users" conjunction, and it must be checked against how this system
is actually deployed** (see §9, the precondition).

---

## 4. Our own licence status — **this is the decisive finding**

I read our root `LICENSE` / `COPYING` / `NOTICE` (absent), root `pyproject.toml`,
`README.md`, `docs/`, and the per-app manifests. Here is what we actually are.

### 4.1 There is no root licence file

A repository-wide search for tracked files named `LICENSE`/`COPYING`/`NOTICE` (any
extension) returns **zero results**. There is no `LICENSE`, no `COPYING`, no `NOTICE` at the
root of `C:\Users\tim\Desktop\COGNITIVE\1`.

### 4.2 Our root `pyproject.toml` declares no licence

`pyproject.toml:16-24`, verbatim and complete:

```toml
[project]
name = "cognitive"
version = "0.1.0"
description = "Global OSINT intelligence platform (workspace root)"
requires-python = ">=3.11"
dependencies = []
```

There is no `license` key, no `license-files`, no `classifiers` entry. Contrast this directly
with the donor's `pyproject.toml`, which at least has the courtesy of disagreeing with itself
out loud. Ours is silent.

### 4.3 Our `README.md` states no licence

`README.md` is 74 lines covering layout, quick start, specs, documentation, and governance.
It contains **no licence statement of any kind**. The Governance section (`README.md:71-73`)
points at `specs/` and `docs/adr/` and says nothing about licensing.

### 4.4 One partial and *conflicting* licence declaration exists

`apps/acquisition/Cargo.toml:14-17`:

```toml
[workspace.package]
version = "0.1.0"
edition = "2021"
license = "MIT"
```

Eight Rust member crates inherit this via `license.workspace = true`
(`contracts`, `observation-gate`, `worker-http`, `worker-browser`, `dispatcher`, `frontier`,
`discovery`, `content-router`).

**So: the acquisition workspace (the Rust half of the system) is marked MIT. The Python
half, the web app, and the root project are undeclared. The repository as a whole has no
licence.**

### 4.5 The verdict

| Component | Declared licence | Evidence |
| --- | --- | --- |
| Root project | **None (unlicensed)** | no root `LICENSE`; `pyproject.toml:16-24` has no `license` key |
| `apps/acquisition` + 8 crates | **MIT** | `apps/acquisition/Cargo.toml:17` |
| All other `apps/*`, `bench` | **None (unlicensed)** | no `license` key in their `pyproject.toml` |
| `README.md` | **None** | no licence statement in 74 lines |

**We are not AGPL. We are not GPL. We are not Apache. We are not MIT as a whole. We are
unlicensed at the root, with an isolated MIT declaration on the Rust acquisition workspace.**

This is the decisive fact of the whole analysis, and it inverts the premise in the task
brief. The brief anticipated: *"if we are already AGPL or GPL, the barrier to adoption is far
lower than if we are permissive."* **We are in the worst of the three cases: we are not
permissive, we are *unspecified*.**

Why that is worse than being permissive, technically:

1. **We hold no outbound licence grant to protect.** A permissive licence (MIT/Apache) is a
   deliberate, public, irrevocable decision to let anyone do anything. Being unlicensed means
   the default is full copyright reservation. When we later add an AGPL-derived file, §5(c)
   binds "the whole of the work ... regardless of how they are packaged" — and "the whole of
   the work" currently has no licence at all, so §5(c) would be the *first* thing to
   characterise it, and it would characterise it as AGPL.
2. **The MIT declaration is an active contradiction, not a neutral absence.**
   `apps/acquisition/Cargo.toml:17` says MIT. §5(b) (`LICENSE:205-208`) requires the conveyed
   work to carry prominent notices that it "is released under this License." You cannot
   simultaneously ship `license = "MIT"` metadata for a crate and satisfy an AGPL §5(b)
   prominent notice for a work that is AGPL. These are incompatible declarations in the same
   artifact. This is not a theoretical concern — it is a metadata conflict that a human
   reviewer will hit the moment a copied file lands near the Rust workspace.
3. **`donors/` is not gitignored.** `.gitignore` covers Python/Rust/Node artefacts, env, keys,
   and data, but contains no `donors/` rule. The tree already holds **88 tracked files** under
   `donors/` (currently `TraceMatrix` plus four others). `donors/estorides/` itself is
   currently untracked — 0 tracked files, confirmed — so nothing has been conveyed *from this
   donor* yet. That is a fact worth protecting, not a fact to leave to chance.

**The pre-existing exposure is not zero, but it is contained.** `donors/TraceMatrix` is
tracked and is GPL/LGPL-class; a verbatim tracked GPL copy in a repo is at most a §4 notice
question for that donor, not a §5(c) whole-work relicensing, because nothing is adapted. The
acute risk is `donors/estorides/` specifically, because the entire proposal is to *adapt*
it. Keep it untracked until the precondition in §9 is settled.

---

## 5. The three options and their real consequences

### Option (a) — direct code copy

**Mechanism:** copy the file, or copy it and adapt it to the 021 contract. This is the literal
reading of the brief's instruction (see §7).

**Consequence:** §5(a)-(d) attach the moment the result is conveyed.

**What exactly becomes AGPL.** Quoting `LICENSE:210-216` again, because this is the sentence
that decides it:

> You must license the entire work, as a whole, under this
> License to anyone who comes into possession of a copy.  This
> License will therefore apply, along with any applicable section 7
> additional terms, to the whole of the work, and all its parts,
> regardless of how they are packaged.

Concretely, under option (a) the AGPL label would attach to:

- the copied file itself;
- your adaptations to it, and any file that imports or links the adaptation;
- **and, via "the entire work, as a whole ... regardless of how they are packaged", the
  workspace it is conveyed in** — in practice the Python apps, the Rust acquisition
  workspace, the web app, and anything packaged alongside.

**The word that does the damage is "regardless of how they are packaged."** It is drafted to
close the "but it's in a different package/directory/repo" defence. If the adapted file and
our substrate are conveyed together, §5(c) reaches the whole thing. If the adapted file is
conveyed *alone* as a separate artifact that merely imports nothing of ours, the blast
radius is that artifact.

**Two hard blockers specific to this repository:**

1. **The MIT conflict.** `apps/acquisition/Cargo.toml:17` (`license = "MIT"`) cannot coexist
   with §5(b)'s requirement to carry prominent AGPL notices. This must be edited before any
   copy lands, not after.
2. **The root is unlicensed.** §5(c) would make the root project AGPL-3.0 as a side effect
   of adopting one file. That is a company-level decision, not an engineering one.

**§13 exposure under (a):** if we run a modified estorides behind our network and our users
reach it remotely, `LICENSE:542-551` requires the prominent source offer, with no
distribution-based escape. Our platform is explicitly a multi-service network system
(`README.md:3-5`, an "event-driven ... distributed OSINT intelligence fabric"), so if option
(a) is chosen, **§13 must be treated as live by default**, not as an edge case.

### Option (b) — clean-room reimplementation from a written specification

**Mechanism:** never look at the donor's source while writing ours. Work from a specification
that describes *what* the mechanism must do (inputs, outputs, invariants, bounds), and
implement it independently.

**Consequence:** the result is **not a derivative work**. The reasoning is textual, not
intuitive. `LICENSE:72-75` defines a "modified version" / work "based on" the earlier work as
one produced by copying from or adapting the work. `LICENSE:223-231` calls a combined work an
"aggregate" when the parts are "separate and independent ... not combined with it such as to
form a larger program." A clean-room implementation is precisely the case where no copying
and no adaptation occurred, so the §5 conditions never attach.

**What makes it clean-room in practice — the positive discipline:**

1. **A written specification exists first, and it is behavioural, not structural.** It
   specifies: inputs and their types, outputs and their exact shape, error modes, bounds and
   limits, invariants, and conformance tests. It must be *implementable by someone who has
   never seen the donor.* That is the test. If the spec could only be satisfied by copying
   the original's file layout, class names, or function decomposition, it is not a
   specification — it is a transcription.
2. **The implementer has not read the donor source.** Not skimmed, not "took a quick look at
   `parsers.py` for ideas." Not read. This is a hard gate, and under agentic development it
   is a *process* control, not an intention: the implementing agent must not have the donor
   files in its context.
3. **Adversarial independent implementations exist before comparison.** Where the spec is
   genuinely behavioural, two independent implementations from the spec should both satisfy
   the conformance suite. If only one approach works, the spec was under-determined and
   smuggled structure in.
4. **Conformance is tested against the spec's stated behaviour, not against the donor's
   output on arbitrary inputs.** Comparing outputs wholesale on a broad corpus is a
   derivative-work risk, because matching behaviour on inputs nobody specified is evidence of
   copying structure.

**What we must NOT do (this is the failure mode that destroys clean-room status):**

- ❌ Read the donor source, then write "similar" code. This is adaptation under
  `LICENSE:72-75`, and it produces a modified version. Similarity of structure, naming, and
  decomposition is the evidence; the §5 conditions attach to the result regardless of how
  independently it was typed.
- ❌ Read the source, then write a spec *describing that source's structure*, then implement
  the spec. The spec is contaminated at the moment it is written. A spec derived from
  reading code is not a clean-room specification; it is a copy in prose form.
- ❌ Have one agent read the donor and a second agent "implement independently from the
  summary." The summary carries the donor's structure. This is laundering, and the
  laundering is visible in the artefacts.
- ❌ Copy tests, fixtures, docstrings, comments, commit messages, or identifiers. These are
  part of the work under `LICENSE:68-70` and are the easiest way to contaminate a
  "clean" implementation by accident.

**The honest limitation of option (b), stated plainly:** it delivers the *mechanisms*, not
the *code*. The brief's premise is that the donor contains 179 source definitions, 50+
parsers, async transport, retry/backoff, circuit breaker, and a SQLite cache, and that
reusing this "can sharply reduce the volume of new code" (`input.md:842`). Option (b) will
**not** deliver that reduction. It will deliver the same capability at a much higher cost in
engineering hours. Anyone choosing (b) must accept that the central economic argument of the
brief does not survive. That trade must be made knowingly, which is why the precondition in
§9 exists.

### Option (c) — run the donor as an external service and call it over its API

**Mechanism:** do not copy, do not vendor, do not link. Deploy estorides (unmodified, or
modified and separately hosted by whoever hosts it) as a service we consume over HTTP.

**What the licence requires of a network user: nothing, in the pure-call case.** The analysis
rests on two quotes.

First, `LICENSE:87-89`:

> To "convey" a work means any kind of propagation that enables other
> parties to make or receive copies.  Mere interaction with a user through
> a computer network, with no transfer of a copy, is not conveying.

We receive responses over HTTP. No copy of the AGPL work moves to us in the act of calling.
So no conveyance by us, and §4/§5/§6 never attach.

Second, `LICENSE:542-544`:

> Notwithstanding any other provision of this License, if you modify the
> Program, your modified version must prominently offer all users
> interacting with it remotely through a computer network ...

§13 is conditioned on *"if you modify the Program"* and runs to the operator toward *its*
users. If we merely call an **unmodified** separately-hosted instance, we are not the
operator, we are not a modifier, and we are not a user of the program in the §13 sense — we
are a client of a service. **§13 does not bite us.**

**So does §13 bite if we merely call an unmodified separately-hosted instance? No.** Three
qualifications, and the first is the one that will actually bite:

1. **We must not modify it.** If our operators fork estorides, patch it, or wrap it in a way
   that constitutes modification, and *we host it*, §13 attaches to us as the operator of a
   modified version serving remote users. Calling our own modified instance is not option
   (c); it is option (a) with extra steps. The "separately-hosted" and "unmodified" qualifiers
   are load-bearing, not decorative.
2. **Who operates it matters.** If the donor or a third party operates and modifies it, the
   source-offer duty is theirs. That is a fact about their deployment, not about our use.
3. **Practical limit.** Option (c) only works if estorides actually exposes the capabilities
   we need as an API. Its `README.md`/project structure indicate a Flask app with a web UI
   and JSON endpoints, but the exact API surface must be verified before this option is
   chosen — a service that only offers a UI is not callable as a service, and vendoring it
   locally to get at the internals collapses option (c) into option (a). **This is a
   feasibility question that must be answered empirically, not assumed.**

### 5.4 Which option permits which activity

Reading of AGPL-3.0 as set out above. "OK" = permitted without a relicensing consequence for
our own work. "Conditional" = permitted only with conditions attached. "No" = not permitted
without the §5(c) whole-work consequence.

| Activity | (a) copy + adapt | (b) clean-room reimplement | (c) call as a service |
| --- | --- | --- | --- |
| **Copy a file verbatim into our tree** | Conditional — permitted, but once conveyed it is a conveyed AGPL work; §4 notice obligations apply | **OK** — not applicable; copying is definitionally excluded | **OK** — we do not copy |
| **Copy a file, then adapt it to the 021 contract** | **No** — this is option (a); §5(c) makes the entire work AGPL "regardless of how they are packaged" | **OK** — if no source was read; this is the whole point of clean-room | **OK** — we do not adapt it |
| **Read a file, then write similar code** | **No** — adaptation under `LICENSE:72-75`; produces a modified version | **No** — the single most common way clean-room status is lost. Must not read the source at all. | **OK** — reading is always free |
| **Read a file, then write a structural spec, then implement it** | **No** — same as above, plus the spec is a contaminated artefact | **No** — the spec was derived from the source, so the implementation is too | **OK** — not applicable |
| **Call an unmodified, separately-hosted instance over its API** | n/a — we already have the code | **OK** — no interaction with the licence | **OK** — `LICENSE:87-89`: "Mere interaction ... is not conveying"; §13 conditioned on "if you modify" |
| **Call a modified instance that we host** | n/a | **No** — this is option (a) in service form | **No** — `LICENSE:542-544` makes us the operator owing the source offer to our remote users |
| **Vendor it into our build/distribution** | **No** — breaks the "aggregate" status at `LICENSE:223-231` ("combined ... such as to form a larger program"); §5(c) then reaches the whole work | **OK** — there is nothing of theirs to vendor | **No** — vendoring is copying, which is option (a) |
| **Link it** (import, `use`, crate dep, in-process call) | **No** — linking forms a combined work; §5(c) whole-work relicensing; `LICENSE:163-165`: "Sublicensing is not allowed" | **OK** — nothing of theirs is linked | **No** — linking requires the code locally |
| **Place it on a shared volume untracked and unused** | **OK** — an "aggregate" under `LICENSE:223-231`; "Inclusion of a covered work in an aggregate does not cause this License to apply to the other parts of the aggregate" | **OK** — same | **OK** — same |

The bottom row of that table is the current state of `donors/` and is analysed in §6.

---

## 6. The `donors/` hazard

**Question: does the presence of an AGPL codebase inside our own tree, even untracked and
unused, create any obligation?**

**Answer: no. The presence alone creates no obligation.** This is stated by the licence
rather than inferred. `LICENSE:223-231`:

> A compilation of a covered work with other separate and independent
> works, which are not by their nature extensions of the covered work,
> and which are not combined with it such as to form a larger program,
> in or on a volume of a storage or distribution medium, is called an
> "aggregate" if the compilation and its resulting copyright are not
> used to limit the access or legal rights of the compilation's users
> beyond what the individual works permit.  Inclusion of a covered work
> in an aggregate does not cause this License to apply to the other
> parts of the aggregate.

"**in or on a volume of a storage or distribution medium**" covers our filesystem exactly.
"Inclusion of a covered work in an aggregate does not cause this License to apply to the
other parts of the aggregate" is an explicit, on-point statement that the *rest of the
repository* is unaffected. Our substrate is not "by its nature an extension" of an OSINT
aggregator, and is not combined with it into a larger program. It is an aggregate.

**The three conditions that must all hold for this to remain true, and the engineer-visible
event that breaks each:**

1. *"not by their nature extensions of the covered work"* — breaks if we start importing,
   vendoring, or linking. No current import path exists; the donor has its own
   `pyproject.toml` with its own dependency set and is not a workspace member (our root
   `pyproject.toml:2-14` lists 11 members, none of them estorides).
2. *"not combined with it such as to form a larger program"* — breaks if the donor is
   packaged into a shipped artifact, a container image, a wheel, or a release alongside our
   apps. The moment `donors/estorides/` ends up in a distribution tarball, the aggregate
   analysis is over.
3. *"the compilation and its resulting copyright are not used to limit the access or legal
   rights of the compilation's users beyond what the individual works permit"* — breaks if
   we add a repo-wide gate that, say, forces AGPL terms on downstream users of the whole
   repo. A blanket "this repo is AGPL" assertion would break this and would also be a
   self-inflicted §5(c) problem.

**The real hazard is not presence — it is a workflow accident.** `donors/` has **no
gitignore rule**. The repo already tracks 88 files under `donors/`. The accident sequence is:
an agent mines the donor, copies a file, and `git add` sweeps in the donor tree as collateral,
or someone tidies up and adds the "reference" donor. Consequences:

- A **verbatim** pushed copy is only a §4 notice problem (`LICENSE:185-191`) — carry the
  copyright notice, keep the notices intact, ship the licence. Annoying, survivable, and
  importantly **not** a whole-work relicensing.
- A **modified** pushed copy is the §5(c) disaster. The distinction between these two is
  entirely about whether the file was adapted, and adaptation is the entire point of the
  proposal.

**Recommendation on the hazard:** add a `donors/` rule to `.gitignore` (or, if donors must
stay visible, an explicit allowlist) **after** the precondition in §9 is settled. Note that
`TraceMatrix` is *already tracked*, so a blanket `donors/` ignore will not untrack it and
`git ls-files` will still list it; that pre-existing condition is out of scope for this
document and should be raised separately. I am not making that change here — this document
is read-only apart from itself, as instructed.

**Scale note, because the brief understated it.** The brief said `donors/` contains "20+
other donor projects". It contains **106** directories. A scan of the top-level licence file
in each:

| Licence class | Count |
| --- | --- |
| MIT/Expat | 39 |
| **No licence file found** | **28** |
| **GPL/LGPL** | **18** |
| Apache | 11 |
| **AGPL** | **4** |
| Other/unrecognised | 4 |
| BSD | 1 |
| MPL | 1 |

So estorides is one of **4 AGPL donors** and one of **26 copyleft-or-unknown donors** in a
106-directory tree. Two points follow. First, the clean-room discipline in option (b) is not
a one-donor problem: it must be applied to all 26, and the **28 donors with no licence file**
are a separate hazard of their own — no licence file means no grant at all, which is
*stricter* than copyleft for reuse purposes, not more permissive. Second, any plan of the
form "we will do a licence audit" is materially larger than the brief implies.

---

## 7. What the brief requires that the licence may forbid

### 7.1 The passage

`specs/022-estorides-donor-mining/input.md:800-804`, verbatim:

```
Я бы **не переписывал 021** ради этого.

В существующие задачи просто добавляется принцип:

> **каждое task implementation-first анализирует donor code и переиспользует существующий implementation, если он удовлетворяет контракту 021 после адаптации.**
```

Translation: *"I would **not rewrite 021** for this. Into the existing tasks we simply add the principle: **each task, implementation-first, analyses donor code and reuses the existing implementation, if it satisfies the 021 contract after adaptation.**"*

Supporting passages that make the intent unambiguous:

`input.md:19`:

> **«021 — конституционный каркас, estorides — массив готовых implementation primitives, которые мы переплавляем в наши контракты».**

*"021 is the constitutional frame, estorides is an array of ready-made implementation
primitives that we reforge into our contracts."*

`input.md:792`:

> **estorides supplies mechanisms; 021 supplies ontology-free semantics, epistemology, identity, lifecycle and provenance.**

`input.md:317`, on `entity_resolution.py`:

> алгоритм matching-а можно практически забрать.

*"the matching algorithm can practically be taken."*

And `input.md:842`, the economic premise:

> Это может резко сократить объём нового кода.

*"This can sharply reduce the volume of new code."*

### 7.2 What the brief requires, in licence terms

Decomposing "**анализирует donor code**" (analyses donor code) and "**переиспользует
существующий implementation ... после адаптации**" (reuses the existing implementation after
adaptation):

- "analyses donor code" — the task **reads the AGPL source**. Permitted (§9: no obligation
  to even accept the licence in order to receive or run a copy). Free.
- "reuses the existing implementation" — the task **incorporates the implementation itself**,
  not a re-derivation. This is copying.
- "after adaptation" (`после адаптации`) — the task **modifies** it to meet the 021 contract.
  This is `LICENSE:72-75` modification in plain words.

Read the two operative words together, the instruction is **copy + modify**, which is
precisely option (a), which is precisely the case `LICENSE:210-216` answers with "You must
license the entire work, as a whole, under this License ... to the whole of the work, and all
its parts, regardless of how they are packaged."

**It is worth recording that the brief already half-anticipates this.** `input.md:722-732`:

```
# Но есть ОДНА фундаментальная вещь, которую нельзя делать

Не надо:

```text
git merge estorides
```

и потом пытаться превратить получившийся монолит в нашу систему.
```

*"But there is ONE fundamental thing that must not be done. Do not: `git merge estorides`,
and then try to turn the resulting monolith into our system."* The brief forbids the
**wholesale architectural merge** on engineering grounds. It does not distinguish that from
**file-level copy-and-adapt**, which is a different act with a different licence consequence —
and which is what its own principle at line 804 actually instructs. That gap is the finding.

### 7.3 Does the request survive AGPL?

**Yes, but only under two conditions, and neither is the one the brief assumes.**

**It survives under option (a) if and only if the entire workspace is first relicensed to
AGPL-3.0.** That is not a workaround; it is exactly what §5(c) requires, and it is the only
reading under which "copy + adapt + convey" is lawful. If the team will accept an AGPL-3.0
workspace, the brief's request is directly executable — and §13 must then be designed for
from day one, not retrofitted.

**It survives under option (b) only if the word "переиспользует" is rewritten to mean
"reimplements from a specification."** That is a real edit to the brief's principle, and it
removes the "sharply reduce the volume of new code" benefit that motivates the whole
proposal. I am not going to pretend otherwise.

**It does not survive as written under our current licence posture.** We are unlicensed at the
root with `license = "MIT"` on the Rust acquisition workspace. Option (a) executed today
would, on the first push, make the whole workspace AGPL-3.0 and contradict our own metadata.
The request is not forbidden by AGPL — it is *incompatible with our current declared state*.

**It survives under option (c) only in a form the brief does not ask for**, since (c) yields
no code reuse and depends on an API surface that has not been verified to exist.

**And the part that survives all options:** the architectural direction. The brief's actual
insight — that our epistemic pipeline (Observation → Context → Mention → Signal → Hypothesis
→ Candidate → Validation → Admission → Claim → Projection, `input.md:747-758`) should be
*ours* while the donor supplies acquisition/parsing/extraction mechanics — is completely
licence-free. That separation of concerns is the project's real asset and it survives
intact. What does not survive is the instruction to achieve it by copying.

---

## 8. Recommendation

**One mode: option (b) — clean-room reimplementation from a written specification — adopted as
the default for estorides and, given §6, for all 26 copyleft-or-unknown donors.**

**Reasoning, in order of weight:**

1. **Our root is unlicensed and our Rust workspace is MIT.** Under §5(c), "regardless of how
   they are packaged", option (a) would convert the entire workspace to AGPL-3.0 as a side
   effect of adopting one file, and would contradict `apps/acquisition/Cargo.toml:17`. A mode
   that silently changes the licence of a whole multi-language monorepo must not be the
   default mode of a routine development workflow. It should be available, deliberately, after
   a business decision — not as the default behaviour of "each task reuses the existing
   implementation."
2. **The default must be the option that fails safe.** Option (b) is the only one of the three
   whose failure mode is *less code reuse* rather than *an unannounced licence change*.
3. **Option (b) preserves the `donors/` aggregate.** Nothing is combined into a larger
   program, so `LICENSE:223-231` keeps holding, and the hazard in §6 stays contained.
4. **The architectural value is independent of the code.** The brief's central claim — that
   021's epistemic pipeline should dominate and the donor should supply only mechanisms
   (`input.md:760`, "мы используем estorides снизу вверх, а не тащим его архитектуру сверху в
  низ" / "we use estorides bottom-up, rather than dragging its architecture top-down") — is
   fully preserved under (b). The separation of concerns is the asset.
5. **The clean-room discipline is a process we must build anyway.** With 106 donors, 26 of them
   copyleft or unknown, we need a written-specification-plus-independent-implementation
   pipeline regardless of what we decide about estorides. Adopting it for this donor is
   incremental, not a new burden.

**What I am explicitly not recommending, and the cost of this choice.** Option (b) will not
deliver the "sharply reduce the volume of new code" outcome that is the brief's main
economic argument. The 50+ parsers and 179 source definitions will have to be written by us.
That is a real and large cost and it must be accepted knowingly by whoever chooses it. My
recommendation is (b) because the licence posture makes (a) a decision that should be made
deliberately by a human, not as a default — **not** because (b) is cheap. If the team,
having read this, decides the AGPL conversion is acceptable, then **option (a) is a perfectly
valid choice** and would deliver what the brief actually wants. What must not happen is
arriving at (a) by accident, through an agent following line 804.

**Option (c) is not recommended** — it yields no code reuse and depends on an unverified API
surface. It remains worth a spike to establish feasibility, and its finding would strengthen
(b) by supplying behavioural specifications.

---

## 9. The one precondition that must be settled before any code moves

**Decide, in writing, the licence of the entire `cognitive` workspace — and reconcile the MIT
declaration — before a single byte of `donors/estorides/` is copied, adapted, imported,
vendored, or linked.**

This is one precondition, not several, because they are one decision with three
manifestations that currently contradict each other:

1. **The root has no licence** (`pyproject.toml:16-24`; no root `LICENSE`/`COPYING`/`NOTICE`
   anywhere in the repo). Decide: AGPL-3.0, MIT, Apache-2.0, proprietary/all-rights-reserved,
   or a deliberate "unlicensed until launch".
2. **`apps/acquisition/Cargo.toml:17` says `license = "MIT"`.** Under AGPL §5(b) a conveyed
   work must carry prominent notices that it "is released under this License". An MIT
   declaration and an AGPL §5(b) notice cannot both be true of the same artifact. Whichever
   way the root decision goes, this line must be changed to match — **before** any AGPL-derived
   file lands anywhere near that workspace.
3. **Repository visibility is unverified and it determines whether conveyance has already
   occurred.** `origin` is `https://github.com/JewishTT/1.git`. I could not determine whether
   this repository is public or private (the `gh` CLI is not installed in this environment, and
   the task forbade git operations). This matters immediately: per `LICENSE:87-89` and
   `LICENSE:80-85`, *pushing* a copy to a remote others can read **is** conveyance. If this
   repo is public, then anything copied in and pushed has been conveyed, and §5 attaches now.
   If it is private with no third-party access, §5 is deferred but not avoided. **Confirm
   visibility as part of this decision.**

**Until that precondition is settled, the standing constraints are:**

- `donors/estorides/` stays **untracked and unmodified** (it is currently untracked — 0
  tracked files — and that state must be preserved).
- No file is copied, adapted, imported, vendored, or linked from `donors/estorides/` into any
  `apps/*` workspace, including the Rust acquisition workspace.
- No agent may implement "021" work from reading the donor source under a
  "reimplement independently" framing; §5 of this document explains why reading first defeats
  clean-room status.
- The `pyproject.toml:10` vs `LICENSE:1-4` metadata disagreement is escalated to a human, not
  resolved by an agent.

**A human being competent to give legal advice must confirm the reading in this document
before any of it is acted on.**
