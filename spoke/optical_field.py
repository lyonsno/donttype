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


OpticalFieldState = Literal["rest", "materialize", "dismiss"]
OpticalFieldDisturbanceMode = Literal["persistent", "ephemeral"]
OpticalFieldCoordinateSpace = Literal[
    "display_points",
    "screen_points",
    "backing_pixels",
    "parent_points",
    "content_points",
]

_COORDINATE_SPACES = {
    "display_points",
    "screen_points",
    "backing_pixels",
    "parent_points",
    "content_points",
}


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
class OpticalFieldCoordinateContext:
    """Coordinate custody metadata for geometry crossing into House."""

    coordinate_space: OpticalFieldCoordinateSpace = "display_points"
    display_id: str | int | None = None
    display_epoch: str | int | None = None
    source_epoch: str | int | None = None
    backing_scale: float | None = None
    display_origin: tuple[float, float] | None = None
    parent_origin: tuple[float, float] | None = None
    content_origin: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.coordinate_space not in _COORDINATE_SPACES:
            raise ValueError(f"unknown optical coordinate space: {self.coordinate_space}")
        if self.backing_scale is not None and self.backing_scale <= 0.0:
            raise ValueError("backing_scale must be positive")
        for field_name in ("display_origin", "parent_origin", "content_origin"):
            origin = getattr(self, field_name)
            if origin is not None:
                if len(origin) != 2:
                    raise ValueError(f"{field_name} must contain x and y")
                object.__setattr__(
                    self,
                    field_name,
                    (float(origin[0]), float(origin[1])),
                )

    @property
    def carries_metadata(self) -> bool:
        return (
            self.coordinate_space != "display_points"
            or self.display_id is not None
            or self.display_epoch is not None
            or self.source_epoch is not None
            or self.backing_scale is not None
            or self.display_origin is not None
            or self.parent_origin is not None
            or self.content_origin is not None
        )


def _require_origin(
    context: OpticalFieldCoordinateContext,
    attr: str,
    space: str,
) -> tuple[float, float]:
    origin = getattr(context, attr)
    if origin is None:
        raise ValueError(f"{space} bounds require {attr}")
    return origin


def normalize_optical_field_bounds(
    bounds: OpticalFieldBounds,
    context: OpticalFieldCoordinateContext | None = None,
) -> OpticalFieldBounds:
    """Normalize explicit coordinate-space bounds into display-local points."""

    context = context or OpticalFieldCoordinateContext()
    space = context.coordinate_space
    if space == "display_points":
        return bounds
    if space == "screen_points":
        display_x, display_y = _require_origin(context, "display_origin", space)
        return OpticalFieldBounds(
            x=bounds.x - display_x,
            y=bounds.y - display_y,
            width=bounds.width,
            height=bounds.height,
        )
    if space == "backing_pixels":
        if context.backing_scale is None:
            raise ValueError("backing_pixels bounds require backing_scale")
        scale = context.backing_scale
        return OpticalFieldBounds(
            x=bounds.x / scale,
            y=bounds.y / scale,
            width=bounds.width / scale,
            height=bounds.height / scale,
        )
    if space == "parent_points":
        parent_x, parent_y = _require_origin(context, "parent_origin", space)
        return OpticalFieldBounds(
            x=bounds.x + parent_x,
            y=bounds.y + parent_y,
            width=bounds.width,
            height=bounds.height,
        )
    if space == "content_points":
        content_x, content_y = _require_origin(context, "content_origin", space)
        return OpticalFieldBounds(
            x=bounds.x + content_x,
            y=bounds.y + content_y,
            width=bounds.width,
            height=bounds.height,
        )
    raise ValueError(f"unknown optical coordinate space: {space}")


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
    coordinate_context: OpticalFieldCoordinateContext = field(
        default_factory=OpticalFieldCoordinateContext
    )
    content_frame: OpticalFieldBounds | None = None
    content_coordinate_context: OpticalFieldCoordinateContext | None = None
    visible: bool = True
    z_index: int = 0

    def __post_init__(self) -> None:
        if not self.caller_id:
            raise ValueError("caller_id must be non-empty")
        if not self.role:
            raise ValueError("role must be non-empty")
        object.__setattr__(self, "disturbances", tuple(self.disturbances))
        if self.content_frame is not None and self.content_coordinate_context is None:
            object.__setattr__(
                self,
                "content_coordinate_context",
                self.coordinate_context,
            )


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


def _bounds_dict(bounds: OpticalFieldBounds) -> dict[str, float]:
    return {
        "x": float(bounds.x),
        "y": float(bounds.y),
        "width": float(bounds.width),
        "height": float(bounds.height),
    }


def _coordinate_metadata(
    request: OpticalFieldRequest,
    bounds: OpticalFieldBounds,
    content_frame: OpticalFieldBounds | None,
) -> dict[str, Any]:
    context = request.coordinate_context
    include_metadata = context.carries_metadata or content_frame is not None
    if not include_metadata:
        return {}
    metadata: dict[str, Any] = {
        "coordinate_space": "display_points",
        "source_coordinate_space": context.coordinate_space,
        "bounds": _bounds_dict(bounds),
    }
    if content_frame is not None:
        metadata["content_frame"] = _bounds_dict(content_frame)
    if context.display_id is not None:
        metadata["display_id"] = context.display_id
    if context.display_epoch is not None:
        metadata["display_epoch"] = context.display_epoch
    if context.source_epoch is not None:
        metadata["source_epoch"] = context.source_epoch
    if context.backing_scale is not None:
        metadata["backing_scale"] = float(context.backing_scale)
    return metadata


def compile_placeholder_shell_config(request: OpticalFieldRequest) -> dict[str, Any]:
    """Compile one contract request into the current legacy shell-config shape."""

    slot_name = _slot_name_for_state(request.state)
    params = _merged_profile_params(request.profile, slot_name)
    bounds = normalize_optical_field_bounds(request.bounds, request.coordinate_context)
    content_frame = (
        normalize_optical_field_bounds(
            request.content_frame,
            request.content_coordinate_context,
        )
        if request.content_frame is not None
        else None
    )
    scale = bounds.min_dimension
    corner_radius = min(
        scale * _float_param(params, "corner_radius_frac"),
        bounds.height * 0.5,
        bounds.width * 0.5,
    )
    exterior_mix = scale * _float_param(params, "exterior_mix_frac")

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
        "optical_field": {
            "caller_id": request.caller_id,
            "profile": request.profile.base,
            "state": request.state,
            "slot": slot_name,
            "disturbances": tuple(
                disturbance.disturbance_id for disturbance in request.disturbances
            ),
            **_coordinate_metadata(request, bounds, content_frame),
        },
    }


class OpticalFieldPlaceholderBackend:
    """In-memory placeholder backend for consumers targeting the new contract."""

    def __init__(
        self,
        *,
        display_epochs: Mapping[str | int, str | int] | None = None,
        source_epochs: Mapping[str | int, str | int] | None = None,
    ) -> None:
        self._requests: dict[str, OpticalFieldRequest] = {}
        self._display_epochs = dict(display_epochs or {})
        self._source_epochs = dict(source_epochs or {})

    def _validate_epoch_context(self, context: OpticalFieldCoordinateContext) -> None:
        display_id = context.display_id
        if display_id is None:
            return
        current_display_epoch = self._display_epochs.get(display_id)
        if (
            current_display_epoch is not None
            and context.display_epoch != current_display_epoch
        ):
            raise ValueError(
                f"stale display_epoch for {display_id}: "
                f"{context.display_epoch!r} != {current_display_epoch!r}"
            )
        current_source_epoch = self._source_epochs.get(display_id)
        if (
            current_source_epoch is not None
            and context.source_epoch != current_source_epoch
        ):
            raise ValueError(
                f"stale source_epoch for {display_id}: "
                f"{context.source_epoch!r} != {current_source_epoch!r}"
            )

    def upsert(self, request: OpticalFieldRequest) -> None:
        self._validate_epoch_context(request.coordinate_context)
        if request.content_coordinate_context is not None:
            self._validate_epoch_context(request.content_coordinate_context)
        self._requests[request.caller_id] = request

    def remove(self, caller_id: str) -> bool:
        return self._requests.pop(caller_id, None) is not None

    def clear(self) -> None:
        self._requests.clear()

    def requests(self) -> tuple[OpticalFieldRequest, ...]:
        return tuple(self._requests.values())

    def compile_shell_configs(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            compile_placeholder_shell_config(request)
            for request in self._requests.values()
            if request.visible
        )
