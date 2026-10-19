import unittest

from integraciones.takyaq_piezo_macos import TakyaqPIStage


class FakePIDevice:
    def __init__(self):
        self.positions = {"A": 10.5, "B": 20.25, "C": 3.0}
        self.moves = []

    def qPOS(self, axes):
        return {axis: self.positions[axis] for axis in axes}

    def MOV(self, axes, values):
        self.moves.append((list(axes), list(values)))
        self.positions.update(zip(axes, values))


class TakyaqPIStageTests(unittest.TestCase):
    def test_translates_nm_to_um_and_waits(self):
        device = FakePIDevice()
        waits = []
        stage = TakyaqPIStage(
            device,
            wait_for_target=lambda device, axes, timeout: waits.append(
                (axes, timeout)
            ),
        )

        self.assertEqual(stage.get_position(), (10500.0, 20250.0, 3000.0))
        stage.set_position_xy(11000.0, 21500.0)

        self.assertEqual(device.moves, [(["A", "B"], [11.0, 21.5])])
        self.assertEqual(waits, [(["A", "B"], 10.0)])
        self.assertEqual(stage.get_position(), (11000.0, 21500.0, 3000.0))

    def test_z_axis_is_c_and_translates_nm_to_um(self):
        device = FakePIDevice()
        stage = TakyaqPIStage(device, axes=("A", "B", "C"))

        stage.set_position_z(4500.0)

        self.assertEqual(device.moves, [(["C"], [4.5])])
        self.assertEqual(stage.get_position(), (10500.0, 20250.0, 4500.0))


if __name__ == "__main__":
    unittest.main()
