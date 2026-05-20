"""Optical lifecycle adapter for the operator overlay.

This module extracts lifecycle decision law from CommandOverlay internals into
a testable adapter. The adapter owns:

  - lifecycle state and event vocabulary
  - retarget-progress decision: when summon arrives during dismiss, what
    progress to re-enter at
  - pending-entrance teardown decision: whether an alpha-zero entrance can
    be torn down without playing dismiss
  - text-plane restore contract shape

It does NOT own:
  - Metal/compositor rendering, SDF fill, or visual tuning
  - AppKit timer management
  - any mutable CommandOverlay state
"""

from __future__ import annotations

import enum
from typing import NamedTuple


class LifecycleState(enum.Enum):
    """Observable lifecycle states of the operator overlay."""

    IDLE_CLOSED = "idle_closed"
    SUMMONING = "summoning"
    IDLE_OPEN = "idle_open"
    DISMISSING = "dismissing"
    DISMISSING_PUCKER = "dismissing_pucker"


class LifecycleEvent(enum.Enum):
    """Events that drive lifecycle transitions."""

    SUMMON = "summon"
    DISMISS = "dismiss"
    MATERIALIZATION_COMPLETE = "materialization_complete"
    PUCKER_COMPLETE = "pucker_complete"


class ToggleIntentAction(enum.Enum):
    """Controller decision for a user toggle intent."""

    DISPATCH = "dispatch"
    IGNORE = "ignore"


class OpticalLifecycleSnapshot(NamedTuple):
    """Small fact snapshot used by the lifecycle controller."""

    visible: bool
    visual_ready_pending: bool
    fade_active: bool
    fade_direction: int
    materialization_active: bool
    materialization_direction: int
    trajectory: str | None = None


class ToggleIntentDecision(NamedTuple):
    """Controller decision plus trace fields for human smoke diagnosis."""

    action: ToggleIntentAction
    reason: str
    trace_fields: dict[str, object]


class PresentationBundleContract(NamedTuple):
    """House-owned coupling law for material body and content plane."""

    owner: str
    mode: str
    body_state: str
    content_state: str
    stable_body_content_split_allowed: bool
    consumer_authored: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "mode": self.mode,
            "body_state": self.body_state,
            "content_state": self.content_state,
            "stable_body_content_split_allowed": self.stable_body_content_split_allowed,
            "consumer_authored": self.consumer_authored,
        }


def presentation_bundle_for_lifecycle_state(
    state: str,
    *,
    visible: bool = True,
) -> PresentationBundleContract:
    """Return the House-owned body/content bundle contract for a public state."""

    if state == "hidden" or not visible:
        mode = "hidden"
        body_state = "hidden"
        content_state = "hidden"
    elif state in {"materialize", "dismiss"}:
        mode = "transitioning"
        body_state = "transitioning"
        content_state = "transitioning"
    else:
        mode = "presented"
        body_state = "presented"
        content_state = "presented"
    return PresentationBundleContract(
        owner="house",
        mode=mode,
        body_state=body_state,
        content_state=content_state,
        stable_body_content_split_allowed=False,
        consumer_authored=False,
    )


class OpticalLifecycleController:
    """Thin intent gate for the optical overlay lifecycle.

    The first controller slice owns legality of user toggle intent. Rendering,
    timers, compositor updates, and AppKit mutation still live in CommandOverlay;
    callers submit a snapshot here before dispatching a lifecycle mutation.
    """

    def decide_toggle(
        self,
        snapshot: OpticalLifecycleSnapshot,
    ) -> ToggleIntentDecision:
        fields = {
            "visible": snapshot.visible,
            "visual_ready_pending": snapshot.visual_ready_pending,
            "fade_active": snapshot.fade_active,
            "fade_direction": snapshot.fade_direction,
            "materialization_active": snapshot.materialization_active,
            "materialization_direction": snapshot.materialization_direction,
            "trajectory": snapshot.trajectory,
        }
        if snapshot.visible and snapshot.visual_ready_pending:
            return ToggleIntentDecision(
                ToggleIntentAction.IGNORE,
                "visible_visual_ready_pending",
                fields,
            )
        if (
            snapshot.visible
            and snapshot.fade_active
            and snapshot.fade_direction > 0
        ):
            return ToggleIntentDecision(
                ToggleIntentAction.IGNORE,
                "visible_fade_in_in_flight",
                fields,
            )
        if (
            snapshot.visible
            and snapshot.materialization_active
            and snapshot.materialization_direction >= 0
        ):
            return ToggleIntentDecision(
                ToggleIntentAction.IGNORE,
                "visible_summon_materialization_in_flight",
                fields,
            )
        return ToggleIntentDecision(
            ToggleIntentAction.DISPATCH,
            "toggle_dispatch_allowed",
            fields,
        )


# These constants must match command_overlay.py exactly.  They are
# imported by command_overlay.py so the adapter owns the numeric retarget law.
BODY_READY_PROGRESS = 0.55
MAG_SEED_FRAC = 0.04


class RetargetDecision(NamedTuple):
    """Result of evaluating a summon-during-dismiss retarget."""

    summon_start_progress: float
    was_pre_body: bool


def retarget_progress_for_dismiss(dismiss_progress: float) -> RetargetDecision:
    """Decide the lawful summon re-entry point for a dismiss-in-flight.

    Implements the same law as ``_summon_retarget_progress_for_dismiss_progress``
    in ``command_overlay.py``:

    - Pre-body dismiss (progress < BODY_READY): retarget from tiny seed,
      clamped to MAG_SEED_FRAC.
    - Post-body dismiss (progress >= BODY_READY): retarget capped at
      BODY_READY so the full-open flash is never re-seeded.

    Returns a RetargetDecision so the caller knows both the numeric
    re-entry point and whether the reversal was pre-body.
    """
    p = max(0.0, min(1.0, dismiss_progress))
    if p < BODY_READY_PROGRESS:
        return RetargetDecision(min(p, MAG_SEED_FRAC), True)
    return RetargetDecision(
        summon_start_progress=min(p, BODY_READY_PROGRESS),
        was_pre_body=False,
    )


class PendingEntranceTeardownDecision(NamedTuple):
    """Result of evaluating whether a pending entrance can be torn down."""

    should_teardown: bool
    reason: str


def should_teardown_pending_entrance(
    *,
    has_compositor: bool,
    window_alpha: float,
) -> PendingEntranceTeardownDecision:
    """Decide whether an alpha-zero optical entrance can be silently torn down.

    Implements the gate logic from ``_cancel_pending_optical_entrance_if_invisible``:
    teardown is safe only when a compositor exists and the window is effectively
    invisible (alpha <= 0.001).
    """
    if not has_compositor:
        return PendingEntranceTeardownDecision(
            should_teardown=False,
            reason="no_compositor",
        )
    if window_alpha > 0.001:
        return PendingEntranceTeardownDecision(
            should_teardown=False,
            reason="visible",
        )
    return PendingEntranceTeardownDecision(
        should_teardown=True,
        reason="invisible_with_compositor",
    )


class TextPlaneRestoreDecision(NamedTuple):
    """Whether the text plane needs restoration after an entrance bypass."""

    should_restore: bool
    reason: str


def should_restore_text_plane(
    *,
    compositor_started: bool,
    has_initial_content: bool,
) -> TextPlaneRestoreDecision:
    """Decide whether to restore the text plane after a failed compositor start.

    When the fullscreen compositor fails to start during show(), the AppKit
    local shell must restore the scroll/text layer.  If the caller started
    with known content (initial transcript), the text punchthrough must also
    be disabled.
    """
    if compositor_started:
        return TextPlaneRestoreDecision(
            should_restore=False,
            reason="compositor_owns_entrance",
        )
    return TextPlaneRestoreDecision(
        should_restore=True,
        reason="compositor_failed_with_content" if has_initial_content else "compositor_failed",
    )


def next_state(current: LifecycleState, event: LifecycleEvent) -> LifecycleState:
    """Pure transition function for the overlay lifecycle.

    Returns the next state given the current state and an event.
    Raises ValueError for illegal transitions.
    """
    _TABLE = {
        (LifecycleState.IDLE_CLOSED, LifecycleEvent.SUMMON): LifecycleState.SUMMONING,
        (LifecycleState.SUMMONING, LifecycleEvent.MATERIALIZATION_COMPLETE): LifecycleState.IDLE_OPEN,
        (LifecycleState.SUMMONING, LifecycleEvent.DISMISS): LifecycleState.DISMISSING,
        (LifecycleState.IDLE_OPEN, LifecycleEvent.DISMISS): LifecycleState.DISMISSING,
        (LifecycleState.DISMISSING, LifecycleEvent.SUMMON): LifecycleState.SUMMONING,
        (LifecycleState.DISMISSING, LifecycleEvent.MATERIALIZATION_COMPLETE): LifecycleState.DISMISSING_PUCKER,
        (LifecycleState.DISMISSING_PUCKER, LifecycleEvent.SUMMON): LifecycleState.SUMMONING,
        (LifecycleState.DISMISSING_PUCKER, LifecycleEvent.PUCKER_COMPLETE): LifecycleState.IDLE_CLOSED,
    }
    key = (current, event)
    if key not in _TABLE:
        raise ValueError(
            f"Illegal lifecycle transition: {current.value} + {event.value}"
        )
    return _TABLE[key]
