"""Contract-level optical field requests for compositor-owned UI surfaces.

This module is intentionally above the current Metal/SDF implementation.  It
lets consumers target a stable request/profile/disturbance contract while the
placeholder backend compiles those requests into today's legacy shell-config
dictionaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping


OpticalFieldState = Literal["rest", "materialize", "resize", "recenter", "dismiss", "hidden"]
OpticalFieldDisturbanceMode = Literal["persistent", "ephemeral"]


@dataclass(frozen=True)
class OpticalFieldBounds:
    """Compositor-space logical bounds for one optical field request."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("optical field bounds must have positive width and height")

    @property
    def center_x(self) -> float:
        return self.x + self.width * 0.5

    @property
    def center_y(self) -> float:
        return self.y + self.height * 0.5

    @property
    def min_dimension(self) -> float:
        return min(self.width, self.height)


@dataclass(frozen=True)
class OpticalFieldSlotOverride:
    """Profile-slot overrides expressed in contract-level normalized params."""

    params: Mapping[str, float | str | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True)
class OpticalFieldProfileRef:
    """Named profile plus optional all-slot and per-slot overrides."""

    base: str = "assistant_shell"
    params: Mapping[str, float | str | bool] = field(default_factory=dict)
    slots: Mapping[str, OpticalFieldSlotOverride] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))


@dataclass(frozen=True)
class OpticalFieldDisturbance:
    """Composable field gesture requested by a UI element."""

    disturbance_id: str
    kind: str
    mode: OpticalFieldDisturbanceMode = "ephemeral"
    strength: float = 1.0
    phase: float = 0.0
    params: Mapping[str, float | str | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.disturbance_id:
            raise ValueError("disturbance_id must be non-empty")
        if not self.kind:
            raise ValueError("disturbance kind must be non-empty")
        if self.strength < 0.0:
            raise ValueError("disturbance strength must be non-negative")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True)
class OpticalFieldRequest:
    """Stable request contract consumed by future UI lanes."""

    caller_id: str
    bounds: OpticalFieldBounds
    role: str
    state: OpticalFieldState = "rest"
    profile: OpticalFieldProfileRef = field(default_factory=OpticalFieldProfileRef)
    disturbances: tuple[OpticalFieldDisturbance, ...] = ()
    visible: bool = True
    z_index: int = 0
    source_epoch: int | None = None
    display_epoch: int | None = None
    provisional: bool = False

    def __post_init__(self) -> None:
        if not self.caller_id:
            raise ValueError("caller_id must be non-empty")
        if not self.role:
            raise ValueError("role must be non-empty")
        object.__setattr__(self, "disturbances", tuple(self.disturbances))


@dataclass(frozen=True)
class OpticalFieldTransitionState:
    """Primitive-owned geometry custody for one caller's latest accepted target."""

    target_request: OpticalFieldRequest
    previous_bounds: OpticalFieldBounds
    presented_bounds: OpticalFieldBounds
    target_bounds: OpticalFieldBounds
    pending_request: OpticalFieldRequest | None = None

    @property
    def caller_id(self) -> str:
        return self.target_request.caller_id

    @property
    def source_epoch(self) -> int | None:
        return self.target_request.source_epoch

    @property
    def display_epoch(self) -> int | None:
        return self.target_request.display_epoch


@dataclass(frozen=True)
class OpticalFieldMailboxResult:
    """Acceptance result for a desired-state geometry target."""

    accepted: bool
    reason: str
    state: OpticalFieldTransitionState | None = None


_BASE_PROFILES: dict[str, dict[str, float | str | bool]] = {
    "assistant_shell": {
        "corner_radius_frac": 0.45,
        "core_magnification": 1.16,
        "band_width_frac": 0.080,
        "tail_width_frac": 0.055,
        "ring_amplitude_frac": 0.090,
        "tail_amplitude_frac": 0.030,
        "bleed_zone_frac": 0.78,
        "exterior_mix_frac": 0.22,
        "mip_blur_strength": 1.0,
    },
    "preview_pill": {
        "corner_radius_frac": 0.50,
        "core_magnification": 1.08,
        "band_width_frac": 0.055,
        "tail_width_frac": 0.040,
        "ring_amplitude_frac": 0.055,
        "tail_amplitude_frac": 0.020,
        "bleed_zone_frac": 0.70,
        "exterior_mix_frac": 0.16,
        "mip_blur_strength": 1.0,
    },
    "agent_card": {
        "corner_radius_frac": 0.34,
        "core_magnification": 1.04,
        "band_width_frac": 0.060,
        "tail_width_frac": 0.040,
        "ring_amplitude_frac": 0.050,
        "tail_amplitude_frac": 0.018,
        "bleed_zone_frac": 0.60,
        "exterior_mix_frac": 0.12,
        "mip_blur_strength": 0.65,
    },
    "quiet_chip": {
        "corner_radius_frac": 0.50,
        "core_magnification": 1.02,
        "band_width_frac": 0.035,
        "tail_width_frac": 0.025,
        "ring_amplitude_frac": 0.025,
        "tail_amplitude_frac": 0.010,
        "bleed_zone_frac": 0.45,
        "exterior_mix_frac": 0.08,
        "mip_blur_strength": 0.4,
    },
}


def available_optical_field_profiles() -> tuple[str, ...]:
    return tuple(_BASE_PROFILES)


def _slot_name_for_state(state: OpticalFieldState) -> str:
    if state in {"materialize", "dismiss"}:
        return state
    return "rest"


def _merged_profile_params(profile: OpticalFieldProfileRef, slot_name: str) -> dict[str, Any]:
    try:
        merged = dict(_BASE_PROFILES[profile.base])
    except KeyError as exc:
        raise ValueError(f"unknown optical field profile: {profile.base}") from exc
    merged.update(profile.params)
    slot = profile.slots.get(slot_name)
    if slot is not None:
        merged.update(slot.params)
    return merged


def _float_param(params: Mapping[str, Any], key: str) -> float:
    return float(params[key])


def _bounds_metadata(bounds: OpticalFieldBounds) -> tuple[float, float, float, float]:
    return (float(bounds.x), float(bounds.y), float(bounds.width), float(bounds.height))


def _with_transition_metadata(
    optical_field: dict[str, Any],
    request: OpticalFieldRequest,
    transition: OpticalFieldTransitionState | None,
) -> dict[str, Any]:
    if transition is None:
        return optical_field

    carries_freshness = (
        request.source_epoch is not None
        or request.display_epoch is not None
        or request.provisional
    )
    carries_geometry_custody = (
        request.state in {"resize", "recenter", "hidden"}
        or transition.previous_bounds != transition.target_bounds
        or transition.presented_bounds != transition.target_bounds
    )
    if not carries_freshness and not carries_geometry_custody:
        return optical_field

    optical_field = dict(optical_field)
    transition_payload: dict[str, Any] = {
        "from_bounds": _bounds_metadata(transition.previous_bounds),
        "presented_bounds": _bounds_metadata(transition.presented_bounds),
        "target_bounds": _bounds_metadata(transition.target_bounds),
        "provisional": bool(request.provisional),
    }
    if request.source_epoch is not None:
        transition_payload["source_epoch"] = int(request.source_epoch)
    if request.display_epoch is not None:
        transition_payload["display_epoch"] = int(request.display_epoch)
    optical_field["transition"] = transition_payload
    return optical_field


def compile_placeholder_shell_config(
    request: OpticalFieldRequest,
    transition: OpticalFieldTransitionState | None = None,
) -> dict[str, Any]:
    """Compile one contract request into the current legacy shell-config shape."""

    slot_name = _slot_name_for_state(request.state)
    params = _merged_profile_params(request.profile, slot_name)
    bounds = request.bounds
    scale = bounds.min_dimension
    corner_radius = min(
        scale * _float_param(params, "corner_radius_frac"),
        bounds.height * 0.5,
        bounds.width * 0.5,
    )
    exterior_mix = scale * _float_param(params, "exterior_mix_frac")

    optical_field = _with_transition_metadata(
        {
            "caller_id": request.caller_id,
            "profile": request.profile.base,
            "state": request.state,
            "slot": slot_name,
            "disturbances": tuple(
                disturbance.disturbance_id for disturbance in request.disturbances
            ),
        },
        request,
        transition,
    )

    return {
        "enabled": True,
        "client_id": request.caller_id,
        "role": request.role,
        "z_index": int(request.z_index),
        "content_width_points": float(bounds.width),
        "content_height_points": float(bounds.height),
        "corner_radius_points": float(corner_radius),
        "center_x": float(bounds.center_x),
        "center_y": float(bounds.center_y),
        "core_magnification": _float_param(params, "core_magnification"),
        "band_width_points": scale * _float_param(params, "band_width_frac"),
        "tail_width_points": scale * _float_param(params, "tail_width_frac"),
        "ring_amplitude_points": scale * _float_param(params, "ring_amplitude_frac"),
        "tail_amplitude_points": scale * _float_param(params, "tail_amplitude_frac"),
        "bleed_zone_frac": _float_param(params, "bleed_zone_frac"),
        "exterior_mix_width_points": exterior_mix,
        "mip_blur_strength": _float_param(params, "mip_blur_strength"),
        "optical_field": optical_field,
    }


class OpticalFieldPlaceholderBackend:
    """In-memory placeholder backend for consumers targeting the new contract."""

    def __init__(self) -> None:
        self._transitions: dict[str, OpticalFieldTransitionState] = {}

    @staticmethod
    def _is_newer_epoch(
        request: OpticalFieldRequest,
        current: OpticalFieldTransitionState,
    ) -> bool:
        for key in ("display_epoch", "source_epoch"):
            incoming = getattr(request, key)
            existing = getattr(current, key)
            if incoming is not None and (existing is None or incoming > existing):
                return True
        return False

    @staticmethod
    def _rejection_reason(
        request: OpticalFieldRequest,
        current: OpticalFieldTransitionState | None,
    ) -> str | None:
        if current is None:
            return None
        if (
            request.display_epoch is not None
            and current.display_epoch is not None
            and request.display_epoch < current.display_epoch
        ):
            return "stale_display_epoch"
        if (
            request.source_epoch is not None
            and current.source_epoch is not None
            and request.source_epoch < current.source_epoch
        ):
            return "stale_source_epoch"
        if (
            request.provisional
            and not current.target_request.provisional
            and not OpticalFieldPlaceholderBackend._is_newer_epoch(request, current)
        ):
            return "stale_provisional_after_final"
        return None

    def upsert(
        self,
        request: OpticalFieldRequest,
        *,
        presented_bounds: OpticalFieldBounds | None = None,
    ) -> OpticalFieldMailboxResult:
        current = self._transitions.get(request.caller_id)
        rejection_reason = self._rejection_reason(request, current)
        if rejection_reason is not None:
            return OpticalFieldMailboxResult(
                accepted=False,
                reason=rejection_reason,
                state=current,
            )

        if presented_bounds is not None:
            previous_bounds = presented_bounds
        elif current is not None:
            previous_bounds = current.presented_bounds
        else:
            previous_bounds = request.bounds

        transition = OpticalFieldTransitionState(
            target_request=request,
            previous_bounds=previous_bounds,
            presented_bounds=previous_bounds,
            target_bounds=request.bounds,
            pending_request=None,
        )
        self._transitions[request.caller_id] = transition
        return OpticalFieldMailboxResult(
            accepted=True,
            reason="accepted",
            state=transition,
        )

    def remove(self, caller_id: str) -> bool:
        return self._transitions.pop(caller_id, None) is not None

    def clear(self) -> None:
        self._transitions.clear()

    def requests(self) -> tuple[OpticalFieldRequest, ...]:
        return tuple(transition.target_request for transition in self._transitions.values())

    def transition_for(self, caller_id: str) -> OpticalFieldTransitionState | None:
        return self._transitions.get(caller_id)

    def sample_presented_bounds(self, caller_id: str, bounds: OpticalFieldBounds) -> bool:
        current = self._transitions.get(caller_id)
        if current is None:
            return False
        self._transitions[caller_id] = OpticalFieldTransitionState(
            target_request=current.target_request,
            previous_bounds=current.previous_bounds,
            presented_bounds=bounds,
            target_bounds=current.target_bounds,
            pending_request=current.pending_request,
        )
        return True

    def compile_shell_configs(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            compile_placeholder_shell_config(transition.target_request, transition)
            for transition in self._transitions.values()
            if transition.target_request.visible and transition.target_request.state != "hidden"
        )
