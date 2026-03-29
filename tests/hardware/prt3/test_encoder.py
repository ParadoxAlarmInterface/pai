"""
Smoke tests for paradox.hardware.prt3.encoder.

Verifies that the module imports cleanly and that all encoder stubs raise
NotImplementedError as expected.  Encoder logic tests will be added in
Phase 2 once the functions are implemented.
"""

import pytest

from paradox.hardware.prt3.encoder import (
    encode_arm,
    encode_quick_arm,
    encode_disarm,
    encode_panic_emergency,
    encode_panic_medical,
    encode_panic_fire,
    encode_utility_key,
    encode_area_status_request,
    encode_zone_status_request,
    encode_area_label_request,
    encode_zone_label_request,
    encode_user_label_request,
)


@pytest.mark.parametrize(
    "fn,args",
    [
        (encode_arm, (1, "A", "1234")),
        (encode_quick_arm, (1, "A")),
        (encode_disarm, (1, "1234")),
        (encode_panic_emergency, (1,)),
        (encode_panic_medical, (1,)),
        (encode_panic_fire, (1,)),
        (encode_utility_key, (1,)),
        (encode_area_status_request, (1,)),
        (encode_zone_status_request, (1,)),
        (encode_area_label_request, (1,)),
        (encode_zone_label_request, (1,)),
        (encode_user_label_request, (1,)),
    ],
)
def test_encoder_raises_not_implemented(fn, args):
    """Every encoder stub must raise NotImplementedError until Phase 2."""
    with pytest.raises(NotImplementedError):
        fn(*args)
