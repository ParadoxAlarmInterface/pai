from paradox.connections.ip.stun_session import redact_site_info

SITE_INFO = {
    "site": [
        {
            "email": "john@example.com",
            "module": [
                {"panelSerial": "7106152c", "xoraddr": "abcd"},
                {"panelSerial": "deadbeef", "xoraddr": None},
            ],
        }
    ]
}


def test_redact_site_info_masks_serials_and_email():
    result = redact_site_info(SITE_INFO)

    modules = result["site"][0]["module"]
    assert modules[0]["panelSerial"] == "****152c"
    assert modules[1]["panelSerial"] == "****beef"
    assert result["site"][0]["email"] == "j****@e****.com"


def test_redact_site_info_preserves_other_fields_and_does_not_mutate():
    result = redact_site_info(SITE_INFO)

    assert result["site"][0]["module"][0]["xoraddr"] == "abcd"
    assert SITE_INFO["site"][0]["module"][0]["panelSerial"] == "7106152c"


def test_redact_site_info_output_contains_no_raw_secrets():
    import json

    dumped = json.dumps(redact_site_info(SITE_INFO))

    assert "7106152c" not in dumped
    assert "deadbeef" not in dumped
    assert "john@example.com" not in dumped
