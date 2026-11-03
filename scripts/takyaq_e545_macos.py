"""Takyaq + E-545/E-517 on the MacBook Air.

Run this file by cells in Spyder.  It is intentionally a laboratory template:
the camera calibration and ROI coordinates must be measured for the current
optical setup before enabling feedback.
"""

# %% 1. Install once, outside Python
# In a terminal, using the same Python environment as Spyder:
#
#   python -m pip install git+https://github.com/Stefani-Lab/takyaq.git
#
# The PI gateway is already listed in requirements.txt.  If needed:
#
#   python -m pip install -r requirements.txt

# %% 2. Imports and experiment parameters
import math
import time

import numpy as np

from integraciones.takyaq_piezo_macos import connect_e545_for_takyaq_macos

from takyaq.controllers import PIController
from takyaq.info_types import CameraInfo, ROI
from takyaq.stabilizer import Stabilizer


CAMERA_SERIAL = "4108802838"
CAMERA_TIMEOUT_S = 2.0

# Replace all four values with the calibration of this optical setup.
# Takyaq expects nanometers per camera pixel.
NM_PER_PIXEL_XY = 1.0
NM_PER_PIXEL_Z = 1.0
Z_SPOT_ANGLE_RAD = 0.0

# Replace these example ROIs with coordinates around actual fiducial marks.
XY_ROIS = [
    ROI(min_x=100, max_x=180, min_y=100, max_y=180),
]
# Replace with the ROI around the reflected Z spot.
Z_ROI = ROI(min_x=300, max_x=380, min_y=300, max_y=380)


# %% 3. Minimal Aravis camera adapter
def image_from_aravis_buffer(buffer):
    """Return a tightly packed Mono8 image from an Aravis buffer."""

    width, height = buffer.get_image_width(), buffer.get_image_height()
    padding_x, _ = buffer.get_image_padding()
    data = np.frombuffer(bytes(buffer.get_image_data()), dtype=np.uint8)
    required = height * (width + padding_x)
    if data.size < required:
        raise RuntimeError(
            f"Buffer incompleto: {data.size} bytes; se requieren {required}"
        )
    return data[:required].reshape(height, width + padding_x)[:, :width].copy()


class AravisCamera:
    """Small Takyaq camera adapter using the existing Aravis setup."""

    def __init__(self, serial=CAMERA_SERIAL, timeout_s=CAMERA_TIMEOUT_S):
        import gi

        gi.require_version("Aravis", "0.8")
        from gi.repository import Aravis

        self._aravis = Aravis
        self._timeout_us = int(timeout_s * 1_000_000)
        Aravis.update_device_list()
        devices = [
            (Aravis.get_device_id(i), Aravis.get_device_serial_nbr(i))
            for i in range(Aravis.get_n_devices())
        ]
        matches = [device_id for device_id, device_serial in devices
                   if device_serial == serial]
        if len(matches) != 1:
            raise RuntimeError(
                f"Se esperaba una cámara con serial {serial}; disponibles: {devices}"
            )

        self._camera = Aravis.Camera.new(matches[0])
        if self._camera is None:
            raise RuntimeError("No se pudo abrir la cámara")
        self._camera.clear_triggers()
        self._camera.set_pixel_format_from_string("Mono8")
        if self._camera.get_pixel_format_as_string() != "Mono8":
            raise RuntimeError("La cámara no aceptó Mono8")

    def get_image(self):
        buffer = self._camera.acquisition(self._timeout_us)
        if buffer is None or buffer.get_status() != self._aravis.BufferStatus.SUCCESS:
            raise RuntimeError("Falló la captura de cámara")
        return image_from_aravis_buffer(buffer)

    def close(self):
        """Release the camera reference."""

        self._camera = None


# %% 4. Open camera and stage
camera = AravisCamera()
pidevice, piezo = connect_e545_for_takyaq_macos()

camera_info = CameraInfo(
    nm_ppx_xy=NM_PER_PIXEL_XY,
    nm_ppx_z=NM_PER_PIXEL_Z,
    angle=Z_SPOT_ANGLE_RAD,
)

# Start with a small proportional gain and zero integral gain.
# Do not enable feedback until the signs and magnitudes are verified.
controller = PIController(Kp=(0.05, 0.05, 0.05), Ki=(0.0, 0.0, 0.0))

stabilizer = Stabilizer(
    camera,
    piezo,
    camera_info,
    controller,
    max_displacement=(200.0, 200.0, 200.0),
)


# %% 5. Start the loop and configure the ROIs
stabilizer.start_loop()
stabilizer.set_xy_rois(XY_ROIS)
stabilizer.set_z_roi(Z_ROI)

# Tracking only: Takyaq observes the marks but does not move the stage yet.
stabilizer.enable_xy_tracking()
stabilizer.enable_z_tracking()


# %% 6. Check the image and signs before enabling feedback
image = camera.get_image()
print(
    "image shape:", image.shape,
    "range:", int(image.min()), int(image.max()),
    "position (nm):", piezo.get_position(),
)

# Move manually with:
# stabilizer.move(*piezo.get_position())
#
# If a positive camera displacement makes Takyaq move in the wrong direction,
# stop here and correct the camera/stage orientation or calibration sign.


# %% 7. Enable stabilization
stabilizer.enable_xy_stabilization()
stabilizer.enable_z_stabilization()
print("Takyaq activo. Para observarlo, esperar y revisar callbacks/logs.")


# %% 8. Stop safely
# Run this cell to stop feedback and release both devices.
stabilizer.disable_xy_stabilization()
stabilizer.disable_z_stabilization()
stabilizer.stop_loop()
piezo.close()
camera.close()
