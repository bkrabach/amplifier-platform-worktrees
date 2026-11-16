# Managed Git worktrees

A small reusable Git library for inspect/create/attach/status/remove. It accepts
bounded argv and never invokes a shell. Repository hooks and external diff
helpers are disabled. A file lock in the common Git directory serializes
participating hosts; Git retains its own branch/worktree locking. It performs no
fetch, push, merge, reset, or forced deletion.

Clean inspection (`inspect(mode='clean', ref=...)`) resolves a committed ref
without reading the source index, diffs or untracked files. Create with the returned
`expected_commit` to pin that immutable commit; an optional `ref` must resolve to
the same commit. Dirty files, conflicts and large retained evidence in the source
do not affect this clean route and are not copied or modified.

Existing `expected_revision` callers retain the full inspected snapshot binding
(HEAD, index/worktree diffs, untracked content hashes), even for clean creation.
It is not a Git commit ID and cannot be combined with `expected_commit`.
Default mode starts a clean detached checkout; a requested new branch uses ordinary Git ownership checks. An
explicit `carry_dirty` copies staged/unstaged patches and nonignored untracked
regular files/symlinks. It requires current HEAD and refuses unmerged indexes,
submodules, and index flags it cannot preserve. Originals are never changed.
Untracked capture is bounded to 2000 files / 20 MB; each Git output is bounded to
20 MB and each Git invocation to 30 seconds.

Private durable JSON records and source manifests precede mutation. Patch bytes,
hashes and untracked evidence are retained under the manifest evidenceDirectory.
A partial attempt remains inspectable and is never replayed automatically. Stable
command identities deduplicate create/attach/remove. Existing checkouts may be
attached but do not acquire deletion ownership. App-created cleanup verifies
current repository/path ownership and refuses changed, untracked or ignored files.
Unreferenced detached commits must be retained on a branch/tag or another worktree
before removal. It preserves branches, source folders, manifests and history. The host supplies
active-task/handoff guards and explicit user intent; this library owns no runtime
or permission controller.

`CheckoutNotStarted` distinguishes a refusal before durable admission with no
existing ownership receipt. After admission begins, including an ambiguous
receipt write or lost acknowledgment, failures retain their uncertain/partial
semantics and must never be automatically replayed.

Managed storage must be outside the source checkout. This avoids storing the
manifest itself among the source files being copied. A checkout can be a source
for another checkout under the same managed parent.

Configured clean/smudge/process filters are disabled per invocation, with no source
configuration edits. Inspection, checkout and apply operate on raw Git/worktree
representations. LFS pointers stay pointers in clean checkouts; materialized dirty
files are carried only within the normal explicit-copy bounds.

A host may inject an opaque JSON `execution_host` descriptor at construction. It
is copied into new create/attach records as `executionHost`, never derived from
private machine data by this library. Legacy records are not rewritten. The host
owns identity validation and guards before mutation or runtime admission.

## Standalone development

This standalone project requires Python 3.13 or newer, Git on `PATH`,
and `filelock>=4.2.1,<5` (installed as its sole runtime dependency). With `uv`
available, run the existing real-Git mechanism tests from this directory:

```sh
uv run --extra test pytest
```

`uv build` creates a wheel and source distribution. To check an installed artifact,
install the wheel and the `test` extra in a separate environment, copy `tests/`
there, and run those tests outside this source checkout. Unified and Core are not
required. These tests create synthetic repositories in temporary directories.
Current packaging qualification covers Linux ARM64 with Python 3.13; it does not
establish Windows or macOS acceptance.

## Ownership and provenance

This history-preserving project is prepared as the public author home at
`bkrabach/amplifier-platform-worktrees`, with a later transfer to Microsoft planned.
[PROVENANCE.json](PROVENANCE.json) records the original public Unified source,
pre-move history, and exact imported runtime/test bytes. Original MIT attribution
is preserved. The repository name does not rename the `amplifier-worktrees`
distribution or `amplifier_worktrees` import.

This import changes no runtime behavior, dependency requirement, package version,
or maintained test. Unified retains its host integration and policy. Authoring
handoff and consumer selection are separate reviewed changes; retire Unified’s
authored project at handoff rather than maintain two authoring copies.

Foundation also carries an optional `libraries/worktrees` package. It is a
separate, divergent line: this imported API includes relocation, command locking,
source binding and admission callbacks used by Unified. This move does not replace
Foundation’s library or merge its API; consolidation needs a separate consumer
review. Preserve the imported behavior when updating this repository.

Use a separate environment for this distribution. Do not coinstall it with
`amplifier-unified`, which currently owns its selected `amplifier_worktrees` files.
This source import is not independent pip replacement inside a Unified prefix.

## Existing delivery and future publication

Unified continues to select the immutable [worktrees-v0.1.0 artifacts](https://github.com/microsoft/amplifier-unified/releases/tag/worktrees-v0.1.0)
from their original public producer. The original source receipt, revision,
subdirectory and hashes remain historical identities; this repository does not
republish or relabel those artifacts. Unified’s generated `components/worktrees-delivery/`
is selected by `components/worktrees.source.json` and verified offline during
normal builds. Do not edit that generated copy by hand.

The [package workflow](.github/workflows/package.yml) builds one wheel and source
archive, then tests that wheel outside the checkout. It does not publish a release
or change any consumer. A future publication needs an exact source/artifact
receipt and review of Unified’s selector for this repository-root project layout;
the existing selector identifies historical monorepo subdirectories. Source moves
do not reserve a new version or make the original receipts invalid.

## Project guidance

The original MIT license and Microsoft open-source conduct, security and support
guidance are retained for this eventual Microsoft home. This repository is
currently hosted under `bkrabach`; it does not claim Microsoft organization
automation, CLA enforcement, release service connections or support coverage.
The existing security-reporting guidance is retained; do not post vulnerabilities
in public issues.
