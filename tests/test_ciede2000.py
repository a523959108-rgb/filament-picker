import numpy as np
import pytest

from filament_picker.ciede2000 import delta_e_2000
from filament_picker.colorspace import hex_to_lab

SHARMA_CASES = [
    ((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
    ((50, 3.1571, -77.2803), (50, 0, -82.7485), 2.8615),
    ((50, 2.8361, -74.0200), (50, 0, -82.7485), 3.4412),
    ((50, 0, 0), (50, -1, 2), 2.3669),
    ((50, 2.5, 0), (50, 0, -2.5), 4.3065),
    ((50, 2.5, 0), (73, 25, -18), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
]


@pytest.mark.parametrize(("lab1", "lab2", "expected"), SHARMA_CASES)
def test_sharma_vectors(lab1, lab2, expected):
    assert abs(float(delta_e_2000(lab1, lab2)) - expected) < 1e-4


def test_symmetry_and_identity():
    for lab1, lab2, _ in SHARMA_CASES:
        assert abs(float(delta_e_2000(lab1, lab2)) - float(delta_e_2000(lab2, lab1))) < 1e-9
        assert float(delta_e_2000(lab1, lab1)) == 0.0


def test_broadcasting():
    lab1 = np.array([case[0] for case in SHARMA_CASES], dtype=float)
    lab2 = np.array(SHARMA_CASES[0][1], dtype=float)
    result = delta_e_2000(lab1, lab2)
    assert result.shape == (8,)
    pairwise = delta_e_2000(lab1, np.array([case[1] for case in SHARMA_CASES], dtype=float))
    assert pairwise.shape == (8,)
    for index, case in enumerate(SHARMA_CASES):
        assert pairwise[index] == pytest.approx(float(delta_e_2000(case[0], case[1])))


def test_black_delta():
    actual = float(delta_e_2000(hex_to_lab("#000000"), hex_to_lab("#272729")))
    assert abs(actual - 9.7548) < 1e-3
