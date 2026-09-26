# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Full end-to-end provisioning workflow against a real NIOS grid.

This single test mirrors the documented provision.ibcli workflow:

  1. Add two grid members (pre-provisioned with VNIOS + IB-V4126 + licenses)
  2. Create a DHCP failover association between them
  3. Create a network with both members assigned
  4. Add a DHCP range backed by the failover association
  5. Verify each step via WAPI GET
  6. Tear down everything via cleanup fixtures

Why one big test instead of small isolated ones?
The provisioning steps are causally ordered: ranges require members on the
network, which requires the failover, which requires the members.  Keeping
them together makes the sequencing constraint explicit and gives the clearest
failure signal when something breaks.

All lessons from real-grid debugging are exercised here:
- POST + PUT separation for pre_provisioning
- platform vs hwtype distinction (VNIOS vs IB-V4126)
- lowercase license values
- dict _ref response coercion
- primary_server_type = "GRID" (not default)
- FQDN not IP for failover peers
- Members must be network members before a failover range can reference them
"""

import pytest

from ibcli.dispatcher import process_line


@pytest.fixture
def cleanup_member(grid_ctx):
    to_delete = []
    yield to_delete
    for fqdn in to_delete:
        try:
            members = grid_ctx.session.get("member", host_name=fqdn)
            if members:
                grid_ctx.session.delete(members[0]["_ref"])
        except Exception:
            pass


@pytest.fixture
def cleanup_failover(grid_ctx):
    to_delete = []
    yield to_delete
    for name in to_delete:
        try:
            fos = grid_ctx.session.get("dhcpfailover", name=name)
            if fos:
                grid_ctx.session.delete(fos[0]["_ref"])
        except Exception:
            pass


@pytest.fixture
def cleanup_network(grid_ctx):
    to_delete = []
    yield to_delete
    for cidr in to_delete:
        try:
            nets = grid_ctx.session.get("network", network=cidr)
            if nets:
                grid_ctx.session.delete(nets[0]["_ref"])
        except Exception:
            pass


def test_full_provision_workflow(
    grid_ctx,
    test_prefix,
    cleanup_member,
    cleanup_failover,
    cleanup_network,
    capsys,
):
    """End-to-end provision.ibcli workflow: members → failover → network → range."""
    p_fqdn = f"{test_prefix}-gm1.example.com"
    s_fqdn = f"{test_prefix}-gm2.example.com"
    fo_name = f"{test_prefix}-dhcp-fo"
    cidr = "10.200.99.0/24"
    range_start = "10.200.99.10"
    range_end = "10.200.99.200"

    cleanup_member.extend([p_fqdn, s_fqdn])
    cleanup_failover.append(fo_name)
    cleanup_network.append(cidr)

    # -------------------------------------------------------------------------
    # Step 1 - Add two pre-provisioned grid members
    # Lesson: pre_provisioning must NOT be in the POST body; ibcli sends a
    # separate PUT.  Platform (VNIOS) and hwtype (IB-V4126) are distinct enums.
    # Licenses must be lowercase strings (enterprise, dns, dhcp).
    # -------------------------------------------------------------------------
    for i, fqdn in enumerate([p_fqdn, s_fqdn], start=1):
        process_line(
            f"configure grid Infoblox member add {fqdn} "
            f"ipaddress 10.200.0.{10 + i}/24 gateway 10.200.0.254 "
            f"platform VNIOS hwtype IB-V4126 "
            f"license enterprise license dns license dhcp",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert f"Added member {fqdn}" in out, f"Member add failed for {fqdn}: {out}"
        assert f"Pre-provisioned {fqdn}" in out, f"Pre-provisioning step missing for {fqdn}: {out}"
        assert "Rolled back" not in out, (
            f"Pre-provisioning was rolled back for {fqdn} (check license case): {out}"
        )

    # Verify both members exist and have the correct pre_provisioning data
    for fqdn in [p_fqdn, s_fqdn]:
        members = grid_ctx.session.get(
            "member",
            host_name=fqdn,
            _return_fields=["host_name", "platform", "pre_provisioning"],
        )
        assert len(members) == 1, f"Expected 1 member for {fqdn}, got {len(members)}"
        m = members[0]
        assert m.get("platform") == "VNIOS", f"Expected platform=VNIOS, got {m.get('platform')}"
        pp = m.get("pre_provisioning", {})
        hw = pp.get("hardware_info", [])
        assert hw, f"No hardware_info in pre_provisioning for {fqdn}"
        assert hw[0].get("hwtype") == "IB-V4126", (
            f"Expected hwtype=IB-V4126, got {hw[0].get('hwtype')}"
        )
        lics = pp.get("licenses", [])
        assert "enterprise" in lics, f"Expected 'enterprise' license (lowercase), got {lics}"
        assert "dhcp" in lics, f"Expected 'dhcp' license, got {lics}"

    # -------------------------------------------------------------------------
    # Step 2 - Create DHCP failover association
    # Lesson: primary_server_type/secondary_server_type must be "GRID".
    # primary/secondary must be FQDNs (host_name), not IP addresses.
    # -------------------------------------------------------------------------
    process_line(
        f"configure network failover add {fo_name} primary {p_fqdn} secondary {s_fqdn}",
        grid_ctx,
    )
    out = capsys.readouterr().out
    assert "Error" not in out, f"Failover creation failed: {out}"

    fos = grid_ctx.session.get(
        "dhcpfailover",
        name=fo_name,
        _return_fields=["name", "primary_server_type", "secondary_server_type", "primary"],
    )
    assert len(fos) == 1, f"Expected 1 failover '{fo_name}', got {len(fos)}"
    assert fos[0]["primary_server_type"] == "GRID", (
        f"Expected primary_server_type=GRID, got {fos[0].get('primary_server_type')}"
    )
    assert fos[0]["secondary_server_type"] == "GRID", (
        f"Expected secondary_server_type=GRID, got {fos[0].get('secondary_server_type')}"
    )

    # -------------------------------------------------------------------------
    # Step 3 - Create network with members assigned at creation time
    # Lesson: both failover peers must be network members before a
    # failover-backed range can be created; using ``member`` at creation
    # assigns them immediately.
    # -------------------------------------------------------------------------
    process_line(
        f"configure network add {cidr} "
        f"member 10.200.0.11 member 10.200.0.12 "
        f'comment "{test_prefix}-integration-test"',
        grid_ctx,
    )
    out = capsys.readouterr().out
    assert "Error" not in out, f"Network add failed: {out}"

    nets = grid_ctx.session.get("network", network=cidr)
    assert len(nets) == 1, f"Expected network {cidr} to exist after add"

    # -------------------------------------------------------------------------
    # Step 4 - Add DHCP range backed by the failover association
    # Lesson: range creation fails with "member not in network" if the failover
    # peers weren't pre-assigned as network members above.
    # -------------------------------------------------------------------------
    process_line(
        f"configure network {cidr} range add {range_start} {range_end} failover {fo_name}",
        grid_ctx,
    )
    out = capsys.readouterr().out
    assert "Error" not in out, f"Range add failed: {out}"

    ranges = grid_ctx.session.get(
        "range",
        network=cidr,
        _return_fields=["start_addr", "end_addr", "failover_association"],
    )
    assert len(ranges) == 1, f"Expected 1 range in {cidr}, got {len(ranges)}"
    assert ranges[0]["start_addr"] == range_start, (
        f"Expected start_addr={range_start}, got {ranges[0]['start_addr']}"
    )
    assert ranges[0]["end_addr"] == range_end, (
        f"Expected end_addr={range_end}, got {ranges[0]['end_addr']}"
    )
    assert ranges[0].get("failover_association") == fo_name, (
        f"Expected failover_association={fo_name}, got {ranges[0].get('failover_association')}"
    )
