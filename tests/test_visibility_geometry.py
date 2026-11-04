import numpy as np

from ttc.visibility import segment_occulted


def test_moon_blocks_line_of_sight():
    assert segment_occulted(np.array([-10., 0., 0.]), np.array([10., 0., 0.]),
                            np.zeros(3), radius_km=2.)


def test_moon_does_not_block_offset_ray():
    assert not segment_occulted(np.array([-10., 5., 0.]), np.array([10., 5., 0.]),
                                np.zeros(3), radius_km=2.)
