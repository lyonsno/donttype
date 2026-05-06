from __future__ import annotations

import pytest

from spoke.optical_field import (
    OpticalFieldBounds,
    OpticalFieldDisturbance,
    OpticalFieldPlaceholderBackend,
    OpticalFieldProfileRef,
    OpticalFieldRequest,
    OpticalFieldSlotOverride,
)


def test_placeholder_backend_preserves_contract_identity_and_profile_slot_metadata():
    backend = OpticalFieldPlaceholderBackend()
    request = OpticalFieldRequest(
        caller_id="agent.card.codex-1",
        bounds=OpticalFieldBounds(x=40.0, y=80.0, width=320.0, height=96.0),
        role="agent_card",
        state="rest",
        profile=OpticalFieldProfileRef(
            base="agent_card",
            slots={
                "rest": OpticalFieldSlotOverride(params={"core_magnification": 1.08}),
                "dismiss": OpticalFieldSlotOverride(params={"mip_blur_strength": 0.0}),
            },
        ),
        disturbances=(
            OpticalFieldDisturbance(
                disturbance_id="ready-pulse",
                kind="readiness_pulse",
                mode="ephemeral",
                strength=0.35,
                phase=0.25,
            ),
        ),
        z_index=7,
    )

    backend.upsert(request)

    (shell_config,) = backend.compile_shell_configs()
    assert shell_config["client_id"] == "agent.card.codex-1"
    assert shell_config["role"] == "agent_card"
    assert shell_config["z_index"] == 7
    assert shell_config["content_width_points"] == pytest.approx(320.0)
    assert shell_config["content_height_points"] == pytest.approx(96.0)
    assert shell_config["center_x"] == pytest.approx(200.0)
    assert shell_config["center_y"] == pytest.approx(128.0)
    assert shell_config["core_magnification"] == pytest.approx(1.08)
    assert shell_config["optical_field"] == {
        "caller_id": "agent.card.codex-1",
        "profile": "agent_card",
        "state": "rest",
        "slot": "rest",
        "disturbances": ("ready-pulse",),
    }


def test_profile_slots_override_independently_without_leaking_between_lifecycle_states():
    backend = OpticalFieldPlaceholderBackend()
    profile = OpticalFieldProfileRef(
        base="assistant_shell",
        slots={
            "materialize": OpticalFieldSlotOverride(
                params={"ring_amplitude_frac": 0.20, "mip_blur_strength": 0.25}
            ),
            "dismiss": OpticalFieldSlotOverride(
                params={"ring_amplitude_frac": 0.04, "mip_blur_strength": 0.0}
            ),
        },
    )
    bounds = OpticalFieldBounds(x=10.0, y=20.0, width=600.0, height=180.0)

    backend.upsert(
        OpticalFieldRequest(
            caller_id="assistant",
            bounds=bounds,
            role="assistant",
            state="materialize",
            profile=profile,
        )
    )
    materialize = backend.compile_shell_configs()[0]

    backend.upsert(
        OpticalFieldRequest(
            caller_id="assistant",
            bounds=bounds,
            role="assistant",
            state="dismiss",
            profile=profile,
        )
    )
    dismiss = backend.compile_shell_configs()[0]

    assert materialize["ring_amplitude_points"] == pytest.approx(36.0)
    assert materialize["mip_blur_strength"] == pytest.approx(0.25)
    assert dismiss["ring_amplitude_points"] == pytest.approx(7.2)
    assert dismiss["mip_blur_strength"] == pytest.approx(0.0)


def test_normalized_profile_values_scale_with_geometry_not_raw_preview_tuning():
    backend = OpticalFieldPlaceholderBackend()
    profile = OpticalFieldProfileRef(base="agent_card")

    backend.upsert(
        OpticalFieldRequest(
            caller_id="small",
            bounds=OpticalFieldBounds(x=0.0, y=0.0, width=240.0, height=80.0),
            role="agent_card",
            state="rest",
            profile=profile,
        )
    )
    backend.upsert(
        OpticalFieldRequest(
            caller_id="large",
            bounds=OpticalFieldBounds(x=0.0, y=0.0, width=960.0, height=320.0),
            role="agent_card",
            state="rest",
            profile=profile,
        )
    )

    small, large = backend.compile_shell_configs()
    assert large["ring_amplitude_points"] / small["ring_amplitude_points"] == pytest.approx(4.0)
    assert large["band_width_points"] / small["band_width_points"] == pytest.approx(4.0)
    assert large["corner_radius_points"] / small["corner_radius_points"] == pytest.approx(4.0)


def test_backend_upsert_and_remove_are_stable_by_caller_id():
    backend = OpticalFieldPlaceholderBackend()
    backend.upsert(
        OpticalFieldRequest(
            caller_id="preview",
            bounds=OpticalFieldBounds(x=0.0, y=0.0, width=180.0, height=42.0),
            role="preview",
            state="rest",
        )
    )
    backend.upsert(
        OpticalFieldRequest(
            caller_id="preview",
            bounds=OpticalFieldBounds(x=10.0, y=20.0, width=240.0, height=64.0),
            role="preview",
            state="rest",
        )
    )

    (updated,) = backend.compile_shell_configs()
    assert updated["center_x"] == pytest.approx(130.0)
    assert updated["center_y"] == pytest.approx(52.0)

    assert backend.remove("preview") is True
    assert backend.compile_shell_configs() == ()
    assert backend.remove("preview") is False


def test_placeholder_configs_survive_fullscreen_compositor_snapshot_round_trip():
    from spoke.fullscreen_compositor import (
        OverlayClientIdentity,
        _snapshot_from_shell_config,
        _snapshot_to_shell_config,
    )

    backend = OpticalFieldPlaceholderBackend()
    backend.upsert(
        OpticalFieldRequest(
            caller_id="agent.card.codex-1",
            bounds=OpticalFieldBounds(x=40.0, y=80.0, width=320.0, height=96.0),
            role="agent_card",
            state="rest",
            profile=OpticalFieldProfileRef(base="agent_card"),
        )
    )
    (shell_config,) = backend.compile_shell_configs()

    snapshot = _snapshot_from_shell_config(
        OverlayClientIdentity(
            client_id="agent.card.codex-1",
            display_id=1,
            role="preview",
        ),
        shell_config,
        generation=3,
    )
    round_tripped = _snapshot_to_shell_config(snapshot)

    assert round_tripped["optical_field"] == shell_config["optical_field"]


def _field_request(
    caller_id: str,
    *,
    bounds: OpticalFieldBounds,
    state: str = "rest",
    display_epoch: int = 1,
    source_epoch: int | None = 1,
    provisional: bool = False,
    visible: bool = True,
) -> OpticalFieldRequest:
    return OpticalFieldRequest(
        caller_id=caller_id,
        bounds=bounds,
        role="agent_card",
        state=state,
        profile=OpticalFieldProfileRef(base="agent_card"),
        display_epoch=display_epoch,
        source_epoch=source_epoch,
        provisional=provisional,
        visible=visible,
    )


def _bounds_tuple(bounds: OpticalFieldBounds) -> tuple[float, float, float, float]:
    return (bounds.x, bounds.y, bounds.width, bounds.height)


def test_transition_mailbox_coalesces_same_caller_provisional_geometry_to_latest_target():
    backend = OpticalFieldPlaceholderBackend()
    initial = OpticalFieldBounds(x=20.0, y=30.0, width=240.0, height=80.0)
    older_target = OpticalFieldBounds(x=40.0, y=50.0, width=300.0, height=96.0)
    latest_target = OpticalFieldBounds(x=60.0, y=70.0, width=360.0, height=112.0)

    backend.upsert(_field_request("agent.card.codex-1", bounds=initial, display_epoch=1))
    first_resize = backend.upsert(
        _field_request(
            "agent.card.codex-1",
            bounds=older_target,
            state="resize",
            display_epoch=2,
            source_epoch=2,
            provisional=True,
        )
    )
    second_resize = backend.upsert(
        _field_request(
            "agent.card.codex-1",
            bounds=latest_target,
            state="resize",
            display_epoch=3,
            source_epoch=3,
            provisional=True,
        )
    )

    assert first_resize.accepted is True
    assert second_resize.accepted is True
    (request,) = backend.requests()
    assert request.bounds == latest_target
    transition = backend.transition_for("agent.card.codex-1")
    assert transition is not None
    assert transition.previous_bounds == initial
    assert transition.presented_bounds == initial
    assert transition.target_bounds == latest_target
    assert transition.pending_request is None


def test_transition_mailbox_rejects_stale_display_and_source_epochs_without_replay():
    backend = OpticalFieldPlaceholderBackend()
    accepted_bounds = OpticalFieldBounds(x=10.0, y=10.0, width=200.0, height=60.0)
    stale_display_bounds = OpticalFieldBounds(x=300.0, y=10.0, width=200.0, height=60.0)
    stale_source_bounds = OpticalFieldBounds(x=500.0, y=10.0, width=200.0, height=60.0)

    accepted = backend.upsert(
        _field_request(
            "agent.card.codex-1",
            bounds=accepted_bounds,
            state="resize",
            display_epoch=5,
            source_epoch=10,
        )
    )
    stale_display = backend.upsert(
        _field_request(
            "agent.card.codex-1",
            bounds=stale_display_bounds,
            state="resize",
            display_epoch=4,
            source_epoch=11,
        )
    )
    stale_source = backend.upsert(
        _field_request(
            "agent.card.codex-1",
            bounds=stale_source_bounds,
            state="resize",
            display_epoch=5,
            source_epoch=9,
        )
    )

    assert accepted.accepted is True
    assert stale_display.accepted is False
    assert stale_display.reason == "stale_display_epoch"
    assert stale_source.accepted is False
    assert stale_source.reason == "stale_source_epoch"
    (request,) = backend.requests()
    assert request.bounds == accepted_bounds


def test_transition_mailbox_dismiss_and_hidden_clear_pending_geometry_for_caller():
    backend = OpticalFieldPlaceholderBackend()
    materialize_bounds = OpticalFieldBounds(x=100.0, y=100.0, width=320.0, height=120.0)
    pending_bounds = OpticalFieldBounds(x=180.0, y=140.0, width=420.0, height=140.0)
    dismiss_bounds = OpticalFieldBounds(x=180.0, y=140.0, width=420.0, height=140.0)

    backend.upsert(
        _field_request(
            "preview",
            bounds=materialize_bounds,
            state="materialize",
            display_epoch=1,
            provisional=True,
        )
    )
    backend.upsert(
        _field_request(
            "preview",
            bounds=pending_bounds,
            state="resize",
            display_epoch=2,
            provisional=True,
        )
    )
    dismiss = backend.upsert(
        _field_request(
            "preview",
            bounds=dismiss_bounds,
            state="dismiss",
            display_epoch=3,
            provisional=False,
        )
    )

    assert dismiss.accepted is True
    transition = backend.transition_for("preview")
    assert transition is not None
    assert transition.target_request.state == "dismiss"
    assert transition.target_bounds == dismiss_bounds
    assert transition.pending_request is None

    hidden = backend.upsert(
        _field_request(
            "preview",
            bounds=dismiss_bounds,
            state="hidden",
            display_epoch=4,
            provisional=False,
            visible=False,
        )
    )
    assert hidden.accepted is True
    transition = backend.transition_for("preview")
    assert transition is not None
    assert transition.target_request.state == "hidden"
    assert transition.pending_request is None
    assert backend.compile_shell_configs() == ()


def test_transition_mailbox_interrupts_from_sampled_presented_bounds_not_stale_from_bounds():
    backend = OpticalFieldPlaceholderBackend()
    initial = OpticalFieldBounds(x=0.0, y=0.0, width=240.0, height=80.0)
    first_target = OpticalFieldBounds(x=400.0, y=0.0, width=320.0, height=100.0)
    sampled_presented = OpticalFieldBounds(x=160.0, y=0.0, width=272.0, height=88.0)
    interrupted_target = OpticalFieldBounds(x=160.0, y=220.0, width=300.0, height=96.0)

    backend.upsert(_field_request("assistant", bounds=initial, display_epoch=1))
    backend.upsert(
        _field_request(
            "assistant",
            bounds=first_target,
            state="resize",
            display_epoch=2,
            source_epoch=2,
        )
    )
    backend.sample_presented_bounds("assistant", sampled_presented)
    interrupt = backend.upsert(
        _field_request(
            "assistant",
            bounds=interrupted_target,
            state="recenter",
            display_epoch=3,
            source_epoch=3,
        )
    )

    assert interrupt.accepted is True
    transition = backend.transition_for("assistant")
    assert transition is not None
    assert transition.previous_bounds == sampled_presented
    assert transition.presented_bounds == sampled_presented
    assert transition.target_bounds == interrupted_target

    (shell_config,) = backend.compile_shell_configs()
    metadata = shell_config["optical_field"]["transition"]
    assert metadata["from_bounds"] == pytest.approx(_bounds_tuple(sampled_presented))
    assert metadata["target_bounds"] == pytest.approx(_bounds_tuple(interrupted_target))


def test_transition_mailbox_payload_survives_fullscreen_compositor_snapshot_round_trip():
    from spoke.fullscreen_compositor import (
        OverlayClientIdentity,
        _snapshot_from_shell_config,
        _snapshot_to_shell_config,
    )

    backend = OpticalFieldPlaceholderBackend()
    initial = OpticalFieldBounds(x=20.0, y=30.0, width=240.0, height=80.0)
    sampled_presented = OpticalFieldBounds(x=50.0, y=60.0, width=260.0, height=88.0)
    target = OpticalFieldBounds(x=80.0, y=90.0, width=320.0, height=96.0)

    backend.upsert(_field_request("agent.card.codex-1", bounds=initial, display_epoch=1))
    backend.sample_presented_bounds("agent.card.codex-1", sampled_presented)
    backend.upsert(
        _field_request(
            "agent.card.codex-1",
            bounds=target,
            state="resize",
            display_epoch=2,
            source_epoch=7,
        )
    )
    (shell_config,) = backend.compile_shell_configs()

    snapshot = _snapshot_from_shell_config(
        OverlayClientIdentity(
            client_id="agent.card.codex-1",
            display_id=1,
            role="preview",
        ),
        shell_config,
        generation=4,
    )
    round_tripped = _snapshot_to_shell_config(snapshot)

    assert round_tripped["optical_field"]["transition"]["from_bounds"] == pytest.approx(
        _bounds_tuple(sampled_presented)
    )
    assert round_tripped["optical_field"]["transition"]["target_bounds"] == pytest.approx(
        _bounds_tuple(target)
    )
    assert round_tripped["optical_field"]["transition"]["display_epoch"] == 2
    assert round_tripped["optical_field"]["transition"]["source_epoch"] == 7
