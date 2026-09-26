# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""End-to-end provisioning workflow against a real NIOS grid.

Each test is self-contained: creates its resources, asserts, then deletes.
Tests should be idempotent and leave no residue on the grid.

Lessons locked in by this suite
--------------------------------
- ``fileop`` needs ``Content-Type: application/force-download`` on the
  file-io GET step (test_download_database).
- DHCP failover needs ``primary_server_type``/``secondary_server_type = "GRID"``
  (test_failover_with_fqdn_peers).
- DHCP failover wants member FQDN (host_name), not IP, for primary/secondary
  (test_failover_with_fqdn_peers).
- ``pre_provisioning`` can't be included in the initial member POST - needs
  a separate PUT (test_preprovisioned_member_add).
- License values are lowercase (``enterprise`` not ``ENTERPRISE``)
  (test_license_case_is_preserved).
- ``platform`` (e.g. ``VNIOS``) and ``hwtype`` (e.g. ``IB-V4126``) are
  distinct enums (test_preprovisioned_member_add).
- WAPI POST response may be dict ``{"_ref": "..."}`` not bare string
  (exercised by every create call via ``_coerce_ref`` in session.py).
- Failover-backed ranges require both peers assigned as network members first
  (test_subnet_with_members_and_failover_range).
"""

import pytest

from ibcli.dispatcher import process_line

# ===========================================================================
# Cleanup fixtures (best-effort; do not crash if resource already deleted)
# ===========================================================================


@pytest.fixture
def cleanup_member(grid_ctx):
    """Yields a list; any FQDNs appended to it are deleted in teardown."""
    to_delete = []
    yield to_delete
    for fqdn in to_delete:
        try:
            members = grid_ctx.session.get("member", host_name=fqdn)
            if members:
                grid_ctx.session.delete(members[0]["_ref"])
        except Exception:
            pass  # best-effort cleanup


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


# ===========================================================================
# Member add (locks in: pre_provisioning via POST+PUT, platform/hwtype split,
# lowercase licenses, dict-ref response handling, gateway warning)
# ===========================================================================


class TestMemberAdd:
    def test_plain_member_add(self, grid_ctx, test_prefix, cleanup_member, capsys):
        """POST-only member (no pre_provisioning) must succeed and be verifiable."""
        fqdn = f"{test_prefix}-plain.example.com"
        cleanup_member.append(fqdn)
        process_line(
            f"configure grid Infoblox member add {fqdn} "
            f"ipaddress 10.200.0.1/24 gateway 10.200.0.254",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert f"Added member {fqdn}" in out
        # Verify on the grid
        members = grid_ctx.session.get("member", host_name=fqdn)
        assert len(members) == 1

    def test_preprovisioned_member_add(self, grid_ctx, test_prefix, cleanup_member, capsys):
        """Member add with platform/hwtype/license must do POST then PUT.

        Locks in:
        - pre_provisioning omitted from POST body (grid rejects it there)
        - platform=VNIOS and hwtype=IB-V4126 are distinct enums
        - licenses are lowercase strings (``enterprise``, ``dns``)
        - dict ``{"_ref": "..."}`` POST response is handled by _coerce_ref
        """
        fqdn = f"{test_prefix}-prov.example.com"
        cleanup_member.append(fqdn)
        process_line(
            f"configure grid Infoblox member add {fqdn} "
            f"ipaddress 10.200.0.2/24 gateway 10.200.0.254 "
            f"platform VNIOS hwtype IB-V4126 license enterprise license dns",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert f"Added member {fqdn}" in out
        assert f"Pre-provisioned {fqdn}" in out
        # Verify pre_provisioning on the grid
        members = grid_ctx.session.get(
            "member",
            host_name=fqdn,
            _return_fields=["host_name", "platform", "pre_provisioning"],
        )
        assert len(members) == 1
        m = members[0]
        assert m.get("platform") == "VNIOS"
        pp = m.get("pre_provisioning", {})
        assert pp.get("hardware_info", [{}])[0].get("hwtype") == "IB-V4126"
        assert "enterprise" in pp.get("licenses", [])

    def test_gateway_warning_when_missing(self, grid_ctx, test_prefix, cleanup_member, capsys):
        """Missing gateway must print a visible warning (not an error)."""
        fqdn = f"{test_prefix}-nogw.example.com"
        cleanup_member.append(fqdn)
        process_line(
            f"configure grid Infoblox member add {fqdn} ipaddress 10.200.0.3/24",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert "Warning: no gateway specified" in out

    def test_license_case_is_preserved(self, grid_ctx, test_prefix, cleanup_member, capsys):
        """Lowercase licenses must not be uppercased before the PUT.

        Real grids reject uppercase license values (``ENTERPRISE`` → 400).
        If this regresses, the PUT will 400 and the rollback will print
        "Rolled back" - assert that doesn't happen.
        """
        fqdn = f"{test_prefix}-lc.example.com"
        cleanup_member.append(fqdn)
        process_line(
            f"configure grid Infoblox member add {fqdn} "
            f"ipaddress 10.200.0.4/24 gateway 10.200.0.254 "
            f"platform VNIOS hwtype IB-V4126 license dns license dhcp",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert "Rolled back" not in out  # should succeed, not roll back


# ===========================================================================
# Failover (locks in: primary_server_type=GRID, FQDN not IP)
# ===========================================================================


class TestFailover:
    def test_failover_with_fqdn_peers(
        self,
        grid_ctx,
        test_prefix,
        cleanup_member,
        cleanup_failover,
        capsys,
    ):
        """DHCP failover creation must use FQDN peers and primary_server_type=GRID.

        Locks in:
        - ``primary_server_type``/``secondary_server_type`` = ``"GRID"``
        - ``primary``/``secondary`` are member host_names (FQDNs), not IPs
          (IP strings cause "Member <ip> was not found" from NIOS)
        """
        p_fqdn = f"{test_prefix}-fo1.example.com"
        s_fqdn = f"{test_prefix}-fo2.example.com"
        fo_name = f"{test_prefix}-fo"
        cleanup_member.extend([p_fqdn, s_fqdn])
        cleanup_failover.append(fo_name)

        for i, fqdn in enumerate([p_fqdn, s_fqdn], start=1):
            process_line(
                f"configure grid Infoblox member add {fqdn} "
                f"ipaddress 10.200.0.{100 + i}/24 gateway 10.200.0.254 "
                f"platform VNIOS hwtype IB-V4126 "
                f"license enterprise license dns license dhcp",
                grid_ctx,
            )
            capsys.readouterr()

        process_line(
            f"configure network failover add {fo_name} primary {p_fqdn} secondary {s_fqdn}",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert "Error" not in out

        # Verify on the grid
        fos = grid_ctx.session.get(
            "dhcpfailover",
            name=fo_name,
            _return_fields=["name", "primary_server_type", "primary"],
        )
        assert len(fos) == 1
        assert fos[0]["primary_server_type"] == "GRID"


# ===========================================================================
# Network + range + members (locks in: member at creation, failover sequencing)
# ===========================================================================


class TestNetworkWithFailover:
    def test_subnet_with_members_and_failover_range(
        self,
        grid_ctx,
        test_prefix,
        cleanup_member,
        cleanup_failover,
        cleanup_network,
        capsys,
    ):
        """Network + range with failover works only when members are pre-assigned.

        Locks in:
        - Failover-backed ranges require both peers assigned as network members
          first - creating the range before member assignment causes NIOS to
          reject it.
        - Network add with ``member`` keyword assigns members at creation time.
        """
        p_fqdn = f"{test_prefix}-net1.example.com"
        s_fqdn = f"{test_prefix}-net2.example.com"
        fo_name = f"{test_prefix}-fo"
        cidr = "10.200.50.0/24"
        cleanup_member.extend([p_fqdn, s_fqdn])
        cleanup_failover.append(fo_name)
        cleanup_network.append(cidr)

        for i, fqdn in enumerate([p_fqdn, s_fqdn], start=1):
            process_line(
                f"configure grid Infoblox member add {fqdn} "
                f"ipaddress 10.200.0.{200 + i}/24 gateway 10.200.0.254 "
                f"platform VNIOS hwtype IB-V4126 "
                f"license enterprise license dns license dhcp",
                grid_ctx,
            )
            capsys.readouterr()

        process_line(
            f"configure network failover add {fo_name} primary {p_fqdn} secondary {s_fqdn}",
            grid_ctx,
        )
        capsys.readouterr()

        # Network add with members at creation - the UX improvement
        process_line(
            f"configure network add {cidr} "
            f"member 10.200.0.201 member 10.200.0.202 "
            f'comment "integration-test"',
            grid_ctx,
        )
        assert "Error" not in capsys.readouterr().out

        # Range with failover - should work now that members are assigned
        process_line(
            f"configure network {cidr} range add 10.200.50.10 10.200.50.100 failover {fo_name}",
            grid_ctx,
        )
        out = capsys.readouterr().out
        assert "Error" not in out

        # Verify on the grid
        ranges = grid_ctx.session.get(
            "range",
            network=cidr,
            _return_fields=["start_addr", "end_addr", "failover_association"],
        )
        assert len(ranges) == 1
        assert ranges[0]["start_addr"] == "10.200.50.10"
        assert ranges[0].get("failover_association") == fo_name


# ===========================================================================
# Fileop (locks in: force-download Content-Type, cookie-auth on file-io GET)
# ===========================================================================


class TestFileop:
    def test_download_database(self, grid_ctx, tmp_path, capsys):
        """Database download must succeed and produce a non-trivial file.

        Locks in:
        - ``Content-Type: application/force-download`` header is required on
          the ``http_direct_file_io`` GET step - without it Apache returns 415.
        - Cookie-auth established by the session carries through to the
          file-io endpoint (same host, rewritten if internal IP returned).
        """
        dest = tmp_path / "grid-backup.bak"
        process_line(f"download database {dest}", grid_ctx)
        out = capsys.readouterr().out
        assert "Error" not in out
        assert dest.exists()
        # Real grid backups are tens of MB minimum; sanity check not-trivial.
        assert dest.stat().st_size > 1000
