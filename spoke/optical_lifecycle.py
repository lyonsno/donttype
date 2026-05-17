"""House-owned lifecycle adapter for optical-field consumers.

Consumers publish finite optical-field requests: identity, role, geometry,
profile, presentation, and lifecycle intent. This module is the House side of
that boundary. It keeps mailbox state, compiles requests into today's shell
config shape, and drives the shared transition runner without exposing
consumer-authored progress or phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import optical_transition
from .optical_field import (
    OpticalFieldBounds,
    OpticalFieldMailboxResult,
    OpticalFieldPlaceholderBackend,
    OpticalFieldRequest,
    compile_placeholder_shell_config,
)


_ANIMATED_STATES = {"materialize", "dismiss"}


@dataclass(frozen=True)
class OpticalLifecycleFrame:
    """Compositor-ready configs for one sampled House lifecycle frame."""

    caller_id: str
    shell_configs: tuple[dict[str, Any], ...]
    complete: bool
    body_ready: bool


class OpticalLifecycleAdapter:
    """Primitive-side lifecycle runner for public optical-field requests."""

    def __init__(
        self,
        backend: OpticalFieldPlaceholderBackend | None = None,
    ) -> None:
        self._backend = backend or OpticalFieldPlaceholderBackend()

    def upsert(
        self,
        request: OpticalFieldRequest,
        *,
        presented_bounds: OpticalFieldBounds | None = None,
    ) -> OpticalFieldMailboxResult:
        """Accept or reject a consumer desired state through the House mailbox."""

        return self._backend.upsert(request, presented_bounds=presented_bounds)

    def remove(self, caller_id: str) -> bool:
        return self._backend.remove(caller_id)

    def sample_presented_bounds(
        self,
        caller_id: str,
        bounds: OpticalFieldBounds,
    ) -> bool:
        return self._backend.sample_presented_bounds(caller_id, bounds)

    def frame_at(self, caller_id: str, elapsed_s: float) -> OpticalLifecycleFrame | None:
        """Sample the House-owned lifecycle frame for one optical presence."""

        transition = self._backend.transition_for(caller_id)
        if transition is None:
            return None

        request = transition.target_request
        if not request.visible or request.state == "hidden":
            return OpticalLifecycleFrame(
                caller_id=caller_id,
                shell_configs=(),
                complete=True,
                body_ready=False,
            )

        final_config = compile_placeholder_shell_config(request, transition)
        if request.state not in _ANIMATED_STATES:
            return OpticalLifecycleFrame(
                caller_id=caller_id,
                shell_configs=(final_config,),
                complete=True,
                body_ready=True,
            )

        runner = optical_transition.OpticalTransitionRunner(
            final_config,
            direction=-1 if request.state == "dismiss" else 1,
            client_id=str(final_config.get("client_id", caller_id)),
            role=str(final_config.get("role", request.role)),
            z_index=int(final_config.get("z_index", request.z_index)),
        )
        frame = runner.frame_at(elapsed_s)
        configs = tuple(
            config
            for config in (
                frame.main_config,
                frame.radial_config,
                frame.seam_config,
            )
            if config is not None
        )
        return OpticalLifecycleFrame(
            caller_id=caller_id,
            shell_configs=configs,
            complete=frame.complete,
            body_ready=frame.body_ready,
        )
