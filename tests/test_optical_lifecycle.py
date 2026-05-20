"""Tests for the optical lifecycle adapter.

These are pure decision-law tests: no AppKit, no mocks, no GUI runtime.
They verify the Slitgate invariants as extracted adapter contracts:

  1. Pre-body dismiss reversal re-enters from tiny seed (capped at MAG_SEED_FRAC).
  2. Post-body dismiss reversal never re-seeds full open (capped at BODY_READY).
  3. Pending alpha-zero entrance teardown does not strand a compositor.
  4. Text-plane restore fires when compositor fails.
  5. Transition table matches the landed CommandOverlay trajectory strings.
"""

import pytest

from spoke.optical_lifecycle import (
    BODY_READY_PROGRESS,
    MAG_SEED_FRAC,
    LifecycleEvent,
    LifecycleState,
    OpticalLifecycleController,
    OpticalLifecycleSnapshot,
    ToggleIntentAction,
    next_state,
    retarget_progress_for_dismiss,
    should_restore_text_plane,
    should_teardown_pending_entrance,
)


class TestRetargetProgressForDismiss:
    """Pre-body dismiss reversal re-enters from tiny seed."""

    def test_pre_body_low_progress_caps_at_seed(self):
        """Very early dismiss (progress near 0) should retarget at MAG_SEED_FRAC."""
        result = retarget_progress_for_dismiss(0.02)
        assert result.was_pre_body is True
        assert result.summon_start_progress == 0.02  # below seed frac, identity

    def test_pre_body_mid_progress_caps_at_seed(self):
        """Dismiss at 30% (pre-body) should cap retarget at MAG_SEED_FRAC."""
        result = retarget_progress_for_dismiss(0.30)
        assert result.was_pre_body is True
        assert result.summon_start_progress == MAG_SEED_FRAC

    def test_pre_body_just_below_threshold(self):
        """Dismiss just below BODY_READY should still cap at MAG_SEED_FRAC."""
        result = retarget_progress_for_dismiss(BODY_READY_PROGRESS - 0.01)
        assert result.was_pre_body is True
        assert result.summon_start_progress == MAG_SEED_FRAC

    def test_post_body_caps_at_body_ready(self):
        """Post-body dismiss should cap retarget at BODY_READY (never full-open flash)."""
        result = retarget_progress_for_dismiss(0.80)
        assert result.was_pre_body is False
        assert result.summon_start_progress == BODY_READY_PROGRESS

    def test_post_body_at_threshold(self):
        """Dismiss exactly at BODY_READY is post-body."""
        result = retarget_progress_for_dismiss(BODY_READY_PROGRESS)
        assert result.was_pre_body is False
        assert result.summon_start_progress == BODY_READY_PROGRESS

    def test_full_dismiss_near_zero(self):
        """Dismiss at progress 0.0 should retarget at 0.0."""
        result = retarget_progress_for_dismiss(0.0)
        assert result.was_pre_body is True
        assert result.summon_start_progress == 0.0

    def test_full_dismiss_at_one(self):
        """Dismiss at progress 1.0 caps at BODY_READY."""
        result = retarget_progress_for_dismiss(1.0)
        assert result.was_pre_body is False
        assert result.summon_start_progress == BODY_READY_PROGRESS

    def test_clamps_below_zero(self):
        result = retarget_progress_for_dismiss(-0.5)
        assert result.summon_start_progress == 0.0
        assert result.was_pre_body is True

    def test_clamps_above_one(self):
        result = retarget_progress_for_dismiss(1.5)
        assert result.summon_start_progress == BODY_READY_PROGRESS
        assert result.was_pre_body is False


class TestShouldTeardownPendingEntrance:
    """Pending alpha-zero entrance teardown must not strand a compositor."""

    def test_teardown_invisible_with_compositor(self):
        result = should_teardown_pending_entrance(
            has_compositor=True, window_alpha=0.0
        )
        assert result.should_teardown is True
        assert result.reason == "invisible_with_compositor"

    def test_no_teardown_when_visible(self):
        result = should_teardown_pending_entrance(
            has_compositor=True, window_alpha=0.5
        )
        assert result.should_teardown is False
        assert result.reason == "visible"

    def test_no_teardown_without_compositor(self):
        result = should_teardown_pending_entrance(
            has_compositor=False, window_alpha=0.0
        )
        assert result.should_teardown is False
        assert result.reason == "no_compositor"

    def test_boundary_alpha_just_above_threshold(self):
        result = should_teardown_pending_entrance(
            has_compositor=True, window_alpha=0.002
        )
        assert result.should_teardown is False

    def test_boundary_alpha_at_threshold(self):
        result = should_teardown_pending_entrance(
            has_compositor=True, window_alpha=0.001
        )
        assert result.should_teardown is True

    def test_boundary_alpha_just_below_threshold(self):
        result = should_teardown_pending_entrance(
            has_compositor=True, window_alpha=0.0005
        )
        assert result.should_teardown is True


class TestShouldRestoreTextPlane:
    """Text-plane quarantine restores visibility when compositor fails."""

    def test_restore_when_compositor_failed(self):
        result = should_restore_text_plane(
            compositor_started=False, has_initial_content=False
        )
        assert result.should_restore is True
        assert result.reason == "compositor_failed"

    def test_restore_with_initial_content(self):
        result = should_restore_text_plane(
            compositor_started=False, has_initial_content=True
        )
        assert result.should_restore is True
        assert result.reason == "compositor_failed_with_content"

    def test_no_restore_when_compositor_owns(self):
        result = should_restore_text_plane(
            compositor_started=True, has_initial_content=False
        )
        assert result.should_restore is False
        assert result.reason == "compositor_owns_entrance"

    def test_no_restore_when_compositor_owns_with_content(self):
        result = should_restore_text_plane(
            compositor_started=True, has_initial_content=True
        )
        assert result.should_restore is False


class TestNextState:
    """Transition table matches landed CommandOverlay trajectory strings."""

    def test_summon_from_closed(self):
        assert next_state(LifecycleState.IDLE_CLOSED, LifecycleEvent.SUMMON) == LifecycleState.SUMMONING

    def test_materialization_complete_from_summoning(self):
        assert next_state(LifecycleState.SUMMONING, LifecycleEvent.MATERIALIZATION_COMPLETE) == LifecycleState.IDLE_OPEN

    def test_dismiss_from_open(self):
        assert next_state(LifecycleState.IDLE_OPEN, LifecycleEvent.DISMISS) == LifecycleState.DISMISSING

    def test_dismiss_from_summoning(self):
        """Dismiss during summon is legal (e.g. rapid toggle)."""
        assert next_state(LifecycleState.SUMMONING, LifecycleEvent.DISMISS) == LifecycleState.DISMISSING

    def test_summon_retargets_dismiss(self):
        """Summon during dismiss retargets back to summoning."""
        assert next_state(LifecycleState.DISMISSING, LifecycleEvent.SUMMON) == LifecycleState.SUMMONING

    def test_dismiss_completes_to_pucker(self):
        assert next_state(LifecycleState.DISMISSING, LifecycleEvent.MATERIALIZATION_COMPLETE) == LifecycleState.DISMISSING_PUCKER

    def test_pucker_completes_to_closed(self):
        assert next_state(LifecycleState.DISMISSING_PUCKER, LifecycleEvent.PUCKER_COMPLETE) == LifecycleState.IDLE_CLOSED

    def test_summon_during_pucker(self):
        """Summon during pucker retargets back to summoning."""
        assert next_state(LifecycleState.DISMISSING_PUCKER, LifecycleEvent.SUMMON) == LifecycleState.SUMMONING

    def test_illegal_dismiss_from_closed(self):
        with pytest.raises(ValueError, match="Illegal lifecycle transition"):
            next_state(LifecycleState.IDLE_CLOSED, LifecycleEvent.DISMISS)

    def test_illegal_pucker_complete_from_open(self):
        with pytest.raises(ValueError, match="Illegal lifecycle transition"):
            next_state(LifecycleState.IDLE_OPEN, LifecycleEvent.PUCKER_COMPLETE)

    def test_illegal_double_summon(self):
        with pytest.raises(ValueError, match="Illegal lifecycle transition"):
            next_state(LifecycleState.SUMMONING, LifecycleEvent.SUMMON)


class TestHammerToggleCycle:
    """Simulate rapid summon/dismiss hammer-toggling through the adapter."""

    def test_full_cycle(self):
        """idle_closed -> summon -> open -> dismiss -> pucker -> closed."""
        s = LifecycleState.IDLE_CLOSED
        s = next_state(s, LifecycleEvent.SUMMON)
        assert s == LifecycleState.SUMMONING
        s = next_state(s, LifecycleEvent.MATERIALIZATION_COMPLETE)
        assert s == LifecycleState.IDLE_OPEN
        s = next_state(s, LifecycleEvent.DISMISS)
        assert s == LifecycleState.DISMISSING
        s = next_state(s, LifecycleEvent.MATERIALIZATION_COMPLETE)
        assert s == LifecycleState.DISMISSING_PUCKER
        s = next_state(s, LifecycleEvent.PUCKER_COMPLETE)
        assert s == LifecycleState.IDLE_CLOSED

    def test_rapid_retarget_cycle(self):
        """Summon -> dismiss -> retarget summon -> complete."""
        s = LifecycleState.IDLE_CLOSED
        s = next_state(s, LifecycleEvent.SUMMON)
        s = next_state(s, LifecycleEvent.DISMISS)
        assert s == LifecycleState.DISMISSING
        # Retarget
        s = next_state(s, LifecycleEvent.SUMMON)
        assert s == LifecycleState.SUMMONING
        s = next_state(s, LifecycleEvent.MATERIALIZATION_COMPLETE)
        assert s == LifecycleState.IDLE_OPEN

    def test_pucker_retarget(self):
        """Summon during pucker tail retargets to summoning."""
        s = LifecycleState.IDLE_CLOSED
        s = next_state(s, LifecycleEvent.SUMMON)
        s = next_state(s, LifecycleEvent.MATERIALIZATION_COMPLETE)
        s = next_state(s, LifecycleEvent.DISMISS)
        s = next_state(s, LifecycleEvent.MATERIALIZATION_COMPLETE)
        assert s == LifecycleState.DISMISSING_PUCKER
        s = next_state(s, LifecycleEvent.SUMMON)
        assert s == LifecycleState.SUMMONING


class TestOpticalLifecycleController:
    """Controller owns lifecycle intent legality before rendering moves behind it."""

    def test_blocks_toggle_when_visible_summon_materialization_is_in_flight(self):
        controller = OpticalLifecycleController()
        decision = controller.decide_toggle(
            OpticalLifecycleSnapshot(
                visible=True,
                visual_ready_pending=False,
                fade_active=False,
                fade_direction=0,
                materialization_active=True,
                materialization_direction=1,
                trajectory="summoning",
            )
        )

        assert decision.action is ToggleIntentAction.IGNORE
        assert decision.reason == "visible_summon_materialization_in_flight"
        assert decision.trace_fields["trajectory"] == "summoning"

    def test_blocks_toggle_when_visible_entrance_is_waiting_for_visual_ready(self):
        controller = OpticalLifecycleController()
        decision = controller.decide_toggle(
            OpticalLifecycleSnapshot(
                visible=True,
                visual_ready_pending=True,
                fade_active=False,
                fade_direction=0,
                materialization_active=False,
                materialization_direction=0,
                trajectory="summoning",
            )
        )

        assert decision.action is ToggleIntentAction.IGNORE
        assert decision.reason == "visible_visual_ready_pending"

    def test_allows_toggle_when_visible_overlay_is_settled_open(self):
        controller = OpticalLifecycleController()
        decision = controller.decide_toggle(
            OpticalLifecycleSnapshot(
                visible=True,
                visual_ready_pending=False,
                fade_active=False,
                fade_direction=0,
                materialization_active=False,
                materialization_direction=0,
                trajectory="idle_open",
            )
        )

        assert decision.action is ToggleIntentAction.DISPATCH
        assert decision.reason == "toggle_dispatch_allowed"

    def test_allows_recall_when_overlay_is_not_visible_but_dismiss_is_active(self):
        controller = OpticalLifecycleController()
        decision = controller.decide_toggle(
            OpticalLifecycleSnapshot(
                visible=False,
                visual_ready_pending=False,
                fade_active=False,
                fade_direction=0,
                materialization_active=True,
                materialization_direction=-1,
                trajectory="dismissing",
            )
        )

        assert decision.action is ToggleIntentAction.DISPATCH
        assert decision.reason == "toggle_dispatch_allowed"
