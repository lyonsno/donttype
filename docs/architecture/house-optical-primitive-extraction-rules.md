# House Optical Primitive Extraction Rules

This note records the extraction posture for turning the current operator
overlay warp into a reusable House optical primitive. It is not the public
consumer contract; that lives in `docs/optical-field-consumer-contract.md` and
`docs/optical-field-contract.md`. This note is the engineering rule for how to
move behavior out of the incumbent overlay without losing the behavior that
made the prototype worth extracting.

The rule is: reproduce the incumbent surface through the extracted primitive
before treating the primitive as reusable.

## Why This Exists

The operator overlay is currently the highest-fidelity witness for the optical
shell lifecycle. It contains real product truth: summon, dismiss, mid-transition
interruption, pressure-slit materialization, seam/radial release, text
legibility, and compositor readiness behavior that have all been tuned against
human-visible smoke.

The long-term goal is a House-owned primitive that assistant shell, preview,
agent-card, HUD, and future stack-crystallization surfaces can consume without
breeding private lifecycle queues. The dangerous move is to jump straight from
"the overlay works" to "design the universal primitive." That creates a foggy
middle layer where failures can come from the old lifecycle, the new lifecycle,
or the adapter between them.

Extraction therefore proceeds by preserving the incumbent behavior first,
moving ownership second, and generalizing only after the original surface
smokes clean through the new path.

## Extraction Ladder

1. Identify one private behavior that is already carrying product truth.
2. Extract that behavior into a shared House-facing module without changing its
   semantics.
3. Rewire the incumbent operator overlay to consume the extracted surface in
   the same slice.
4. Add a bypass test proving the overlay no longer reaches the old private
   implementation path.
5. Delete duplicate private ownership; keep compatibility aliases only when
   existing tests or callers still need the old names.
6. Smoke the original operator overlay and require behavior reproduction before
   adding another consumer.
7. Only after reproduction passes, promote the extracted surface toward a
   public lifecycle contract for additional House consumers.

The first successful instance is `spoke.optical_transition`: pressure-slit
materialize/dismiss frame generation moved out of `CommandOverlay`, while
`CommandOverlay` now consumes `OpticalTransitionRunner`.

## Non-Negotiable Checks

**Consumer still attached.** A shared module that no production path consumes
is not an extraction. It is a note in code form. The incumbent overlay must use
the extracted path before the slice is considered meaningful.

**Bypass test required.** Add a test that would fail if the incumbent overlay
could keep executing the old private path. For the transition runner, this is
the test that monkeypatches `OpticalTransitionRunner` and proves
`materializationStep_` consumes its frames.

**Duplicate implementation removed.** Do not leave old and new transition math
alive side by side. That is drift waiting to happen. If legacy names remain,
they should alias the shared primitive rather than preserve a second copy.

**Original surface is the oracle.** The first proof is not a new preview, card,
or HUD consumer. The first proof is the operator overlay reproducing the
known-good visual lifecycle through the extracted path.

**One semantic move per smoke.** A slice may preserve behavior while moving
ownership, or change behavior while preserving ownership. It should not do both
unless the behavioral change is tiny, deliberate, and separately witnessed.

## What Counts As Reproduction

For the operator overlay, reproduction means human-visible smoke confirms the
same lifecycle class that motivated the extraction:

- summon materializes the warp and text coherently
- dismiss collapses without leaving text over no warp
- summon during dismiss and dismiss during summon remain coherent
- compositor sidecars for seam/radial release do not strand stale clients
- text legibility remains tied to the optical surface
- readiness timing does not regress into pop-only or blank-shell behavior

Automated tests are necessary but not sufficient for this surface. Visual output
is output. Until there is a stronger rendered-frame witness harness, clean
human smoke of the incumbent overlay is part of the contract.

## What This Does Not Prove

A clean reproduction smoke does not prove the primitive is universal. It proves
that one truth-bearing piece of the incumbent overlay can be owned outside the
overlay without degrading the incumbent behavior.

The next step after reproduction is not "attach every consumer." The next step
is to expose a narrow public lifecycle adapter that one additional consumer can
use without receiving private progress, phase, timer, or geometry-queue
custody. That second consumer must be added with the same discipline: attached
consumer, bypass test, duplicate ownership removed, and original behavior still
smoked.

## Review Posture

Reviewers should distinguish fake extraction from incomplete extraction.

Fake extraction:

- creates a shared module but leaves the incumbent path private
- keeps two live copies of the transition math
- adds a new consumer before the incumbent surface smokes clean
- exposes progress, phase, timer handles, or private geometry queues as public
  consumer inputs

Incomplete but valid extraction:

- moves one behavior into a shared module
- rewires the incumbent surface through that module
- keeps compatibility aliases for old private names
- has tests proving the old path is no longer bypassing the shared primitive
- has not yet generalized the primitive to all consumers

The first category should be rejected. The second category is allowed progress
when it preserves the incumbent visual behavior and moves ownership in the
direction of the House contract.
