from __future__ import annotations

import pytest

from spoke.optical_field import (
    OpticalFieldBounds,
    OpticalFieldMotionIntent,
    OpticalFieldPresentation,
    OpticalFieldProfileRef,
    OpticalFieldRequest,
)


def _stack_card_request(*, state: str = "materialize") -> OpticalFieldRequest:
    return OpticalFieldRequest(
        caller_id="stack.zetesis.demo",
        bounds=OpticalFieldBounds(x=920.0, y=140.0, width=360.0, height=96.0),
        content_frame=OpticalFieldBounds(x=936.0, y=152.0, width=328.0, height=72.0),
        role="tray",
        state=state,
        presentation=OpticalFieldPresentation(layer="hud", order=50),
        profile=OpticalFieldProfileRef(base="quiet_chip"),
        layout_recipe="deck",
        motion=OpticalFieldMotionIntent(strategy="auto"),
        z_index=3,
    )


def test_stack_card_materializes_through_public_house_lifecycle_adapter():
    from spoke.optical_lifecycle import OpticalLifecycleAdapter
    from spoke import optical_transition

    adapter = OpticalLifecycleAdapter()
    result = adapter.upsert(_stack_card_request(state="materialize"))

    assert result.accepted is True
    first = adapter.frame_at("stack.zetesis.demo", 0.0)
    settled = adapter.frame_at(
        "stack.zetesis.demo",
        optical_transition.OPTICAL_MATERIALIZATION_S * 1.2,
    )

    assert first is not None
    assert first.complete is False
    assert first.body_ready is False
    assert len(first.shell_configs) == 1
    seed = first.shell_configs[0]
    assert seed["client_id"] == "stack.zetesis.demo"
    assert seed["role"] == "tray"
    assert seed["presentation_layer"] == "hud"
    assert seed["presentation_order"] == 50
    assert seed["content_width_points"] < 120.0
    assert seed["optical_field"]["caller_id"] == "stack.zetesis.demo"
    assert seed["optical_field"]["layout_recipe"] == "deck"
    assert "progress" not in seed["optical_field"]
    assert "phase" not in seed["optical_field"]

    assert settled is not None
    assert settled.complete is True
    assert settled.body_ready is True
    final = settled.shell_configs[0]
    assert final["content_width_points"] == pytest.approx(360.0)
    assert final["content_height_points"] == pytest.approx(96.0)


def test_stack_card_dismiss_exposes_house_owned_sidecars_without_consumer_phase():
    from spoke.optical_lifecycle import OpticalLifecycleAdapter
    from spoke import optical_transition

    adapter = OpticalLifecycleAdapter()
    adapter.upsert(_stack_card_request(state="rest"))
    adapter.upsert(_stack_card_request(state="dismiss"))

    frame = adapter.frame_at(
        "stack.zetesis.demo",
        optical_transition.OPTICAL_MATERIALIZATION_DISMISS_S * 0.85,
    )

    assert frame is not None
    client_ids = [config["client_id"] for config in frame.shell_configs]
    assert "stack.zetesis.demo" in client_ids
    assert "stack.zetesis.demo.dismiss_seam" in client_ids
    assert "stack.zetesis.demo.dismiss_radial_pucker" in client_ids
    for config in frame.shell_configs:
        assert config["role"] == "tray"
        assert config["optical_field"]["caller_id"] == "stack.zetesis.demo"
        assert "progress" not in config["optical_field"]
        assert "phase" not in config["optical_field"]


def test_lifecycle_adapter_retargets_from_sampled_presented_bounds():
    from spoke.optical_lifecycle import OpticalLifecycleAdapter

    adapter = OpticalLifecycleAdapter()
    adapter.upsert(_stack_card_request(state="rest"))
    adapter.sample_presented_bounds(
        "stack.zetesis.demo",
        OpticalFieldBounds(x=950.0, y=180.0, width=300.0, height=80.0),
    )
    next_request = OpticalFieldRequest(
        caller_id="stack.zetesis.demo",
        bounds=OpticalFieldBounds(x=980.0, y=220.0, width=420.0, height=112.0),
        role="tray",
        state="retarget",
        presentation=OpticalFieldPresentation(layer="hud", order=50),
        profile=OpticalFieldProfileRef(base="quiet_chip"),
        motion=OpticalFieldMotionIntent(strategy="auto"),
    )

    result = adapter.upsert(next_request)
    frame = adapter.frame_at("stack.zetesis.demo", 0.0)

    assert result.accepted is True
    assert result.state is not None
    assert result.state.previous_bounds == OpticalFieldBounds(
        x=950.0,
        y=180.0,
        width=300.0,
        height=80.0,
    )
    assert frame is not None
    transition = frame.shell_configs[0]["optical_field"]["transition"]
    assert transition["from_bounds"] == pytest.approx((950.0, 180.0, 300.0, 80.0))
    assert transition["target_bounds"] == pytest.approx((980.0, 220.0, 420.0, 112.0))
