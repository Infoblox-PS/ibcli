# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

import pytest
from pydantic import BaseModel, Field

from ibcli.utils import (
    arpa_to_net,
    as_dict,
    cidr_family,
    format_extra_field,
    is_arpa,
    net_to_arpa,
    normalize_cidr,
    normalize_cidr_any,
    parse_extra_fields,
)


def test_net_to_arpa_class_c():
    assert net_to_arpa("1.2.3.0/24") == "3.2.1.in-addr.arpa"


def test_arpa_to_net_class_c():
    assert arpa_to_net("3.2.1.in-addr.arpa") == "1.2.3.0/24"


def test_is_arpa_detection():
    # IPv4 reverse
    assert is_arpa("3.2.1.in-addr.arpa") is True
    assert is_arpa("10.in-addr.arpa") is True
    assert is_arpa("in-addr.arpa") is True
    # IPv6 reverse - regression for RFC 6303 v6 zones (fe80::/10, ULA,
    # documentation). Before this, `configure zone add d.f.ip6.arpa`
    # was rejected by NIOS as a forward zone.
    assert is_arpa("d.f.ip6.arpa") is True
    assert is_arpa("8.b.d.0.1.0.0.2.ip6.arpa") is True
    assert is_arpa("ip6.arpa") is True
    # Case-insensitive
    assert is_arpa("3.2.1.IN-ADDR.ARPA") is True
    assert is_arpa("D.F.IP6.ARPA") is True
    # Non-arpa
    assert is_arpa("foo.com") is False
    assert is_arpa("1.2.3.0/24") is False
    # Substring-only must not match
    assert is_arpa("notin-addr.arpa.example.com") is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.2.3.0/24", "1.2.3.0/24"),
        ("1.2.3/24", "1.2.3.0/24"),
        ("1.2/16", "1.2.0.0/16"),
        ("1/8", "1.0.0.0/8"),
        ("10.0.0.0/8", "10.0.0.0/8"),
    ],
)
def test_normalize_cidr_zero_fills_short_forms(raw, expected):
    assert normalize_cidr(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "1.2.3.4",  # no slash
        "/24",  # no IP
        "1.2.3.4/33",  # mask > 32
        "a.b.c.d/24",  # non-numeric
        "",  # empty
    ],
)
def test_normalize_cidr_invalid_raises(bad):
    with pytest.raises(ValueError):
        normalize_cidr(bad)


# ---------------------------------------------------------------------------
# cidr_family tests
# ---------------------------------------------------------------------------


def test_cidr_family_v4():
    assert cidr_family("192.168.1.0/24") == "v4"


def test_cidr_family_v6():
    assert cidr_family("2001:db8::/32") == "v6"


def test_cidr_family_v6_full():
    assert cidr_family("2001:0db8:0000:0000::/64") == "v6"


def test_cidr_family_invalid_raises():
    with pytest.raises(ValueError):
        cidr_family("not-a-cidr")


# ---------------------------------------------------------------------------
# normalize_cidr_any tests
# ---------------------------------------------------------------------------


def test_normalize_cidr_any_v4():
    cidr, family = normalize_cidr_any("1.2.3.0/24")
    assert cidr == "1.2.3.0/24"
    assert family == "v4"


def test_normalize_cidr_any_v4_short_form():
    # Short IPv4 form is expanded then normalized via ipaddress (host bits zeroed)
    cidr, family = normalize_cidr_any("10.0.0/8")
    assert cidr == "10.0.0.0/8"
    assert family == "v4"


def test_normalize_cidr_any_v6_canonicalizes():
    # Mixed-case and expanded form should be canonicalized
    cidr, family = normalize_cidr_any("2001:DB8:0:0::/64")
    assert cidr == "2001:db8::/64"
    assert family == "v6"


def test_normalize_cidr_any_v6_already_canonical():
    cidr, family = normalize_cidr_any("2001:db8::/32")
    assert cidr == "2001:db8::/32"
    assert family == "v6"


# ---------------------------------------------------------------------------
# SPECOPS <n.n.n.n/mm> now accepts IPv6 CIDRs
# ---------------------------------------------------------------------------


def test_specops_cidr_token_matches_ipv6():
    from ibcli.registry import SPECOPS

    pattern = SPECOPS["<n.n.n.n/mm>"]
    assert pattern.search("2001:db8::/64") is not None
    assert pattern.search("::1/128") is not None


def test_specops_cidr_token_still_matches_ipv4():
    from ibcli.registry import SPECOPS

    pattern = SPECOPS["<n.n.n.n/mm>"]
    assert pattern.search("192.168.1.0/24") is not None


# ---------------------------------------------------------------------------
# as_dict tests
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    ref: str = Field(alias="_ref")
    name: str
    comment: str | None = None


def test_as_dict_converts_pydantic_model_using_aliases():
    m = _Model.model_validate({"_ref": "zone_auth/X", "name": "example.com"})
    result = as_dict(m)
    assert result == {"_ref": "zone_auth/X", "name": "example.com"}


def test_as_dict_passes_through_plain_dicts():
    assert as_dict({"a": 1}) == {"a": 1}


def test_as_dict_passes_through_none():
    assert as_dict(None) is None


def test_arpa_to_net_rejects_non_arpa():
    with pytest.raises(ValueError):
        arpa_to_net("not.an.arpa.zone")


def test_net_to_arpa_rejects_non_network():
    with pytest.raises(ValueError):
        net_to_arpa("not-a-network")


def test_normalize_cidr_rejects_non_digit_mask():
    with pytest.raises(ValueError):
        normalize_cidr("1.2.3.0/abc")


def test_normalize_cidr_rejects_too_many_octets():
    with pytest.raises(ValueError):
        normalize_cidr("1.2.3.4.5/24")


def test_normalize_cidr_any_bogus_raises():
    with pytest.raises(ValueError):
        normalize_cidr_any("totally-bogus-cidr")


# --- fields= opt-in ---------------------------------------------------------


def test_parse_extra_fields_absent():
    assert parse_extra_fields("show network failover foo") == []


def test_parse_extra_fields_single():
    assert parse_extra_fields("show network failover foo fields=primary_state") == ["primary_state"]


def test_parse_extra_fields_multiple():
    assert parse_extra_fields("show network failover foo fields=a,b,c") == ["a", "b", "c"]


def test_parse_extra_fields_ignores_empty_entries():
    assert parse_extra_fields("show x fields=a,,b") == ["a", "b"]


def test_format_extra_field_collapses_member_ref():
    assert (
        format_extra_field({"_ref": "member/x", "_struct": "dhcpmember", "ipv4addr": "10.0.0.1"})
        == "10.0.0.1"
    )


def test_format_extra_field_list_of_dicts():
    out = format_extra_field([{"name": "a", "stealth": False}, {"name": "b"}])
    assert "name=a, stealth=False" in out
    assert " | " in out
    assert "name=b" in out


def test_format_extra_field_scalar_list():
    assert format_extra_field(["x", "y", "z"]) == "x, y, z"


# ---------------------------------------------------------------------------
# fields= and pydantic's builtin-collision escaping
#
# 18 SDK models spell the WAPI `type` field as `type_` because `type` is a
# Python builtin. NIOS rejects the escaped spelling outright:
#   Error: Unknown argument/field: 'type_'
# Found by the deep field sweep against a live grid.
# ---------------------------------------------------------------------------


def test_parse_extra_fields_unescapes_trailing_underscore():
    assert parse_extra_fields("show nsgroup all fields=type_") == ["type"]


def test_parse_extra_fields_leaves_normal_names_alone():
    assert parse_extra_fields("show x fields=name,comment") == ["name", "comment"]


def test_parse_extra_fields_handles_a_mixed_list():
    assert parse_extra_fields("show x fields=name,type_,comment") == [
        "name",
        "type",
        "comment",
    ]


def test_parse_extra_fields_drops_an_all_underscore_token():
    """`fields=_` would un-escape to the empty string; drop it instead."""
    assert parse_extra_fields("show x fields=name,_") == ["name"]


def test_parse_extra_fields_strips_only_pydantic_suffix():
    """`type_` is pydantic's escape for the WAPI `type` field; a bare `_` is
    not a suffix to eat, and only one underscore is ever added."""
    assert parse_extra_fields("show x fields=type_,name") == ["type", "name"]
    assert parse_extra_fields("show x fields=type,name") == ["type", "name"]
    # Not something pydantic produces - must not be rewritten into `a`.
    assert parse_extra_fields("show x fields=a__") == ["a_"]
    # A field that is nothing but underscores collapses away rather than
    # being sent as an empty field name.
    assert parse_extra_fields("show x fields=_") == []
