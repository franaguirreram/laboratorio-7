"""Takyaq adapter for the PI E-517/E-545 stage on macOS.

Takyaq uses nanometers and exposes a small stage interface.  PIPython uses
micrometers and the GCS2 commands ``qPOS`` and ``MOV``.  This module keeps
that translation in one place so acquisition scripts can continue using the
native PIPython API.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


class TakyaqPIStage:
    """Expose a PIPython device using Takyaq's piezo interface.

    Parameters
    ----------
    pidevice:
        Connected ``pipython.GCSDevice`` instance.
    axes:
        Hardware axes corresponding to Takyaq's ``(x, y, z)``.  The default
        matches the E-545 setup in this repository: A, B and C.
    wait_for_target:
        Optional function compatible with ``pitools.waitontarget``.  Keeping
        it injectable makes the adapter testable and allows callers to use a
        device-specific wait policy.
    close_device:
        Optional cleanup callback, for example the gateway's
        ``cleanup_gcsdevice``.
    """

    def __init__(
        self,
        pidevice: Any,
        *,
        axes: Sequence[str | None] = ("A", "B", "C"),
        wait_for_target: Callable[..., Any] | None = None,
        wait_timeout: float = 10.0,
        close_device: Callable[[Any], Any] | None = None,
        z_position_nm: float = 0.0,
    ) -> None:
        if len(axes) != 3:
            raise ValueError("axes must contain exactly (x, y, z)")
        if axes[0] is None or axes[1] is None:
            raise ValueError("x and y must map to real hardware axes")
        if len({axis for axis in axes if axis is not None}) != sum(
            axis is not None for axis in axes
        ):
            raise ValueError("each hardware axis may be mapped only once")

        self._device = pidevice
        self._axes = tuple(axes)
        self._wait_for_target = wait_for_target
        self._wait_timeout = float(wait_timeout)
        self._close_device = close_device
        self._z_position_nm = float(z_position_nm)
        self._closed = False

    @property
    def axes(self) -> tuple[str | None, str | None, str | None]:
        """Return the configured hardware mapping as ``(x, y, z)``."""

        return self._axes

    def init(self) -> None:
        """Validate that the device can be queried.

        Takyaq calls this from its worker thread.  The connection itself is
        deliberately opened by the caller, so this method performs no
        connection or servo-state changes.
        """

        self._query_positions_um()

    def get_position(self) -> tuple[float, float, float]:
        """Return the current position in nanometers."""

        positions_um = self._query_positions_um()
        z_nm = positions_um[self._axes[2]] * 1000.0  # type: ignore[index]
        return (
            positions_um[self._axes[0]] * 1000.0,  # type: ignore[index]
            positions_um[self._axes[1]] * 1000.0,  # type: ignore[index]
            z_nm,
        )

    def set_position_xy(self, x: float, y: float) -> None:
        """Move X and Y to absolute nanometer positions."""

        self._move(
            (self._axes[0], self._axes[1]),
            (float(x) / 1000.0, float(y) / 1000.0),
        )

    def set_position_z(self, z: float) -> None:
        """Move Z to an absolute nanometer position.

        The E-545's third axis is C.
        """

        axis = self._axes[2]
        if axis is None:
            raise RuntimeError("Z stabilization requires a configured hardware axis")
        self._move((axis,), (float(z) / 1000.0,))
        self._z_position_nm = float(z)

    def close(self) -> None:
        """Release the PIPython/gateway connection using the supplied cleanup."""

        if not self._closed and self._close_device is not None:
            self._close_device(self._device)
        self._closed = True

    def _query_positions_um(self) -> Mapping[str, float]:
        axes = [axis for axis in self._axes if axis is not None]
        raw = self._device.qPOS(axes)
        positions = dict(raw)
        missing = [axis for axis in axes if axis not in positions]
        if missing:
            raise RuntimeError(
                f"qPOS did not return configured axes: {', '.join(missing)}"
            )
        return {axis: float(positions[axis]) for axis in axes}

    def _move(
        self,
        axes: Sequence[str | None],
        positions_um: Sequence[float],
    ) -> None:
        real_axes = [axis for axis in axes if axis is not None]
        if len(real_axes) != len(positions_um):
            raise ValueError("every requested position must have a hardware axis")
        self._device.MOV(real_axes, list(positions_um))
        if self._wait_for_target is not None:
            self._wait_for_target(
                self._device,
                real_axes,
                timeout=self._wait_timeout,
            )


def connect_e545_for_takyaq_macos(
    *,
    model: str = "E-517",
    wait_timeout: float = 10.0,
    axes: Sequence[str | None] = ("A", "B", "C"),
) -> tuple[Any, TakyaqPIStage]:
    """Connect the E-545 through the macOS-only FTDI gateway.

    This function is only for the MacBook setup documented in
    ``docs/RESUMEN_conexion_E545_macOS.md``.  On a computer where PI's native
    drivers are available, create a regular ``GCSDevice`` and pass it directly
    to ``TakyaqPIStage`` instead.

    Returns ``(pidevice, stage)``.
    """

    from pipython import GCSDevice, pitools
    from pi_ftdi_gateway import PIFtdiGateway, cleanup_gcsdevice

    pidevice = GCSDevice(model, gateway=PIFtdiGateway())
    pidevice.ONL([1, 2, 3], [1, 1, 1])
    stage = TakyaqPIStage(
        pidevice,
        axes=axes,
        wait_for_target=pitools.waitontarget,
        wait_timeout=wait_timeout,
        close_device=cleanup_gcsdevice,
    )
    stage.init()
    return pidevice, stage
