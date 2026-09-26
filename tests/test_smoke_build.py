# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Regression tests for scripts/smoke/build.py - the script generator that
produces the .ibcli batch file a smoke run consumes.

The only invariant we care about here is: every filter-option / filter-
ipv6option line carries *both* a ``match=<opt>:<value>`` (→ NIOS match
expression) *and* a ``rule=<opt>:<value>:<num>`` (→ ``option_list``) for
every scale preset.

Background: a previous iteration of the smoke emitted filter creates with
no rule data at all. NIOS accepted the object but downstream CSV
importers (UDDI / CSP) rejected the rows with::

    FAILED   option_filter row N: (400) Rule list must contain at least
                                       one rule value or a list.

Even after we added ``rule=`` (to populate option_list), those importers
still failed because they require an explicit *expression* - they don't
infer one from ``apply_as_class=True`` + option_list. So the smoke must
emit both. Pin it here.
"""

from __future__ import annotations

import importlib.util
import io
import ipaddress
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BUILD_PY = REPO / "scripts" / "smoke" / "build.py"


def _load_build():
    """Import scripts/smoke/build.py as a module without side-effects.

    build.py imports its sibling ``_shared`` as a top-level module, so we
    must put ``scripts/smoke`` on sys.path before loading.
    """
    import sys

    smoke_dir = str(BUILD_PY.parent)
    if smoke_dir not in sys.path:
        sys.path.insert(0, smoke_dir)
    spec = importlib.util.spec_from_file_location("_smoke_build", BUILD_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _generate(scale: str, phases: list[int] | None = None) -> list[str]:
    """Run build.main() in-process with argv patched. Return non-blank,
    non-comment lines."""
    mod = _load_build()
    import sys

    old_argv = sys.argv
    old_stdout = sys.stdout
    buf = io.StringIO()
    sys.argv = ["build.py", "--scale", scale]
    if phases is not None:
        sys.argv += ["--phases", ",".join(str(p) for p in phases)]
    try:
        sys.stdout = buf
        mod.main()
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
    return [
        ln for ln in buf.getvalue().splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    ]


class TestSmokeRfcReverseZones:
    """Phase 11 emits the RFC 6303 + RFC 6598 locally-served reverse zones.

    The list is fixed by the RFCs, so it's scale-independent. Pin both the
    total count and a handful of canonical anchor zones so a future refactor
    that trims, renames, or rearranges the list fails loudly.
    """

    # Hand-counted from RFC 6303 (v4=24, v6=6) + RFC 6598 (v4=64).
    # RFC 6303 technically lists 25 v4 zones, but ``255.255.255.255.in-
    # addr.arpa`` is dropped because NIOS rejects the create with
    # ``Invalid IPv4 netmask 32.``; see the note in _shared.py.
    EXPECTED_TOTAL = 94

    def test_full_list_emitted(self):
        lines = _generate("tiny", phases=[11])
        zone_adds = [ln for ln in lines if ln.startswith("configure zone add ")]
        assert len(zone_adds) == self.EXPECTED_TOTAL, (
            f"phase 11 emitted {len(zone_adds)} zones; "
            f"expected {self.EXPECTED_TOTAL} (RFC 6303 + RFC 6598)"
        )

    @pytest.mark.parametrize(
        "fqdn",
        [
            # RFC 6303 v4 anchors
            "10.in-addr.arpa",
            "16.172.in-addr.arpa",
            "31.172.in-addr.arpa",
            "168.192.in-addr.arpa",
            "254.169.in-addr.arpa",
            "2.0.192.in-addr.arpa",
            "100.51.198.in-addr.arpa",
            "113.0.203.in-addr.arpa",
            "0.in-addr.arpa",
            "127.in-addr.arpa",
            # RFC 6303 v6 anchors
            "d.f.ip6.arpa",
            "8.e.f.ip6.arpa",
            "b.e.f.ip6.arpa",
            "8.b.d.0.1.0.0.2.ip6.arpa",
            # RFC 6598 CGN anchors (endpoints of the 64.. 127 range)
            "64.100.in-addr.arpa",
            "96.100.in-addr.arpa",
            "127.100.in-addr.arpa",
        ],
    )
    def test_anchor_zone_present(self, fqdn: str):
        lines = _generate("tiny", phases=[11])
        assert any(
            ln.startswith(f"configure zone add {fqdn} ") or ln == f"configure zone add {fqdn}"
            for ln in lines
        ), f"phase 11 missing RFC anchor zone: {fqdn}"

    def test_teardown_deletes_same_zones(self):
        """Phase 11's teardown must delete exactly the zones its build
        emits - no drift between RFC_LOCAL_ZONES and the delete list."""
        import subprocess
        import sys

        # Shell out rather than re-import teardown.py alongside build.py,
        # since both stamp the same _shared module into sys.modules and
        # teardown's module globals would collide otherwise.
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "smoke" / "teardown.py"),
                "--scale",
                "tiny",
                "--phases",
                "11",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        deletes = [
            ln
            for ln in result.stdout.splitlines()
            if ln.startswith("configure zone ") and ln.endswith(" delete")
        ]
        assert len(deletes) == self.EXPECTED_TOTAL


@pytest.mark.parametrize("scale", ["tiny", "small", "full"])
class TestSmokePtrCoverage:
    """Every forward record (A, AAAA, host) the smoke emits must be
    followed by a matching PTR record. PTRs are routed into the RFC 6303
    umbrella reverse zones (10.in-addr.arpa for v4, 8.b.d.0.1.0.0.2.ip6.arpa
    for v6), which phase 11 provisions.
    """

    def _cmd_lines(self, scale: str, phases: list[int]) -> list[str]:
        return [ln for ln in _generate(scale, phases=phases) if ln.startswith("configure ")]

    def test_phase4_a_records_have_v4_ptr(self, scale: str):
        """Every A record line is followed by a PTR into 10.in-addr.arpa
        pointing at the same IP and fqdn."""
        lines = self._cmd_lines(scale, phases=[4])
        a_re = re.compile(r"^configure zone (\S+) add a (\S+) (\S+)$")
        ptr_re = re.compile(r"^configure zone 10\.in-addr\.arpa add ptr (\S+) (\S+)$")
        pairs_found = 0
        for i, ln in enumerate(lines):
            m = a_re.match(ln)
            if not m:
                continue
            zone, host, ip = m.group(1), m.group(2), m.group(3)
            assert i + 1 < len(lines), f"A record with no following PTR at line {i}: {ln}"
            ptr_m = ptr_re.match(lines[i + 1])
            assert ptr_m, f"Expected PTR after A record; got: {lines[i + 1]!r}"
            assert ptr_m.group(1) == ip, (
                f"PTR IP mismatch at line {i + 1}: A used {ip}, PTR uses {ptr_m.group(1)}"
            )
            assert ptr_m.group(2) == f"{host}.{zone}", (
                f"PTR ptrdname mismatch at line {i + 1}: "
                f"expected {host}.{zone}, got {ptr_m.group(2)}"
            )
            pairs_found += 1
        assert pairs_found > 0, f"scale={scale}: no A records found in phase 4"

    def test_phase4_aaaa_records_have_v6_ptr(self, scale: str):
        """Every AAAA record line is followed by a PTR into
        8.b.d.0.1.0.0.2.ip6.arpa."""
        lines = self._cmd_lines(scale, phases=[4])
        aaaa_re = re.compile(r"^configure zone (\S+) add aaaa (\S+) (\S+)$")
        ptr_re = re.compile(
            r"^configure zone 8\.b\.d\.0\.1\.0\.0\.2\.ip6\.arpa add ptr "
            r"(\S+) (\S+)$"
        )
        pairs_found = 0
        for i, ln in enumerate(lines):
            m = aaaa_re.match(ln)
            if not m:
                continue
            zone, host, ip = m.group(1), m.group(2), m.group(3)
            assert i + 1 < len(lines)
            ptr_m = ptr_re.match(lines[i + 1])
            assert ptr_m, f"Expected v6 PTR after AAAA; got: {lines[i + 1]!r}"
            assert ptr_m.group(1) == ip
            assert ptr_m.group(2) == f"{host}.{zone}"
            pairs_found += 1
        assert pairs_found > 0, f"scale={scale}: no AAAA records in phase 4"

    def test_phase5_hosts_have_v4_ptr(self, scale: str):
        """Every host record is followed by an explicit PTR into
        10.in-addr.arpa for parity with A/AAAA phase."""
        lines = self._cmd_lines(scale, phases=[5])
        host_re = re.compile(r"^configure zone (\S+) add host (\S+) (\S+)$")
        ptr_re = re.compile(r"^configure zone 10\.in-addr\.arpa add ptr (\S+) (\S+)$")
        pairs_found = 0
        for i, ln in enumerate(lines):
            m = host_re.match(ln)
            if not m:
                continue
            zone, host, ip = m.group(1), m.group(2), m.group(3)
            assert i + 1 < len(lines)
            ptr_m = ptr_re.match(lines[i + 1])
            assert ptr_m, f"Expected PTR after host; got: {lines[i + 1]!r}"
            assert ptr_m.group(1) == ip
            assert ptr_m.group(2) == f"{host}.{zone}"
            pairs_found += 1
        assert pairs_found > 0, f"scale={scale}: no host records in phase 5"


@pytest.mark.parametrize("scale", ["tiny", "small", "full"])
class TestSmokeFilterLines:
    """Every filter-option line in the generated script must carry both a
    boolean match rule and a served-option rule."""

    _V4_RE = re.compile(
        r"^configure filter option add (smoke-filt-opt-\d+) "
        r'match=vendor-class-identifier:"smoke-class-\d+" '
        r'rule=vendor-class-identifier:"smoke-class-\d+":60$'
    )
    _V6_RE = re.compile(
        r"^configure filter ipv6option add (smoke-filt-v6o-\d+) "
        r'match=dhcp6\.vendor-class:"smoke-v6class-\d+" '
        r'rule=dhcp6\.vendor-class:"smoke-v6class-\d+":16$'
    )

    def test_v4_option_filters_carry_match_and_rule(self, scale: str):
        lines = _generate(scale, phases=[10])
        v4 = [ln for ln in lines if ln.startswith("configure filter option add ")]
        # Scale presets all provision at least one v4 option filter.
        assert v4, f"scale={scale}: no v4 filter-option lines emitted"
        for ln in v4:
            assert self._V4_RE.match(ln), (
                f"scale={scale}: v4 filter line missing match=+rule= pair:\n  {ln}"
            )

    def test_v6_option_filters_carry_match_and_rule(self, scale: str):
        lines = _generate(scale, phases=[10])
        v6 = [ln for ln in lines if ln.startswith("configure filter ipv6option add ")]
        assert v6, f"scale={scale}: no v6 filter-option lines emitted"
        for ln in v6:
            assert self._V6_RE.match(ln), (
                f"scale={scale}: v6 filter line missing match=+rule= pair:\n  {ln}"
            )

    def test_filter_counts_match_scale(self, scale: str):
        """Sanity-check that every configured filter for the scale made it
        into the output - guards against a future refactor quietly dropping
        filters from phase 10."""
        import sys
        from importlib import import_module

        sys.path.insert(0, str(REPO / "scripts" / "smoke"))
        try:
            shared = import_module("_shared")
        finally:
            sys.path.pop(0)
        p = shared.SCALE[scale]

        lines = _generate(scale, phases=[10])
        n_v4 = sum(1 for ln in lines if ln.startswith("configure filter option add "))
        n_v6 = sum(1 for ln in lines if ln.startswith("configure filter ipv6option add "))
        assert n_v4 == p["filters_option"]
        assert n_v6 == p["filters_ipv6option"]


class TestProductionSmokeSafety:
    """Production scale is large enough that generator bugs are expensive.

    Keep these tests focused on static properties of the generated .ibcli
    scripts so they catch bad address math, unsupported command syntax, and
    build/teardown drift before a live-grid run starts.
    """

    def test_production_fixed_addresses_are_valid_hosts_with_valid_macs(self):
        lines = _generate("production", phases=[2])
        fixed_re = re.compile(
            r"^configure network (\S+) fixed add (\S+) "
            r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})$"
        )
        found = 0
        for ln in lines:
            if " fixed add " not in ln:
                continue
            m = fixed_re.match(ln)
            assert m, f"invalid fixed-address line: {ln}"
            net = ipaddress.ip_network(m.group(1), strict=False)
            ip = ipaddress.ip_address(m.group(2))
            assert ip in net, f"{ip} is outside {net}: {ln}"
            assert ip not in (net.network_address, net.broadcast_address), (
                f"{ip} is not a usable host in {net}: {ln}"
            )
            found += 1

        assert found == 250_000

    def test_production_v4_containers_cover_generated_v4_networks(self):
        import sys
        from importlib import import_module

        sys.path.insert(0, str(REPO / "scripts" / "smoke"))
        try:
            shared = import_module("_shared")
        finally:
            sys.path.pop(0)

        p = shared.SCALE["production"]
        containers = [
            ipaddress.ip_network(shared.v4_container_cidr(i))
            for i in range(p["network_containers_v4"])
        ]
        assert containers, "production scale should define v4 network containers"

        for i in range(p["networks_v4"]):
            net = ipaddress.ip_network(shared.v4_network_cidr(i))
            assert any(net.subnet_of(container) for container in containers), (
                f"{net} is not covered by any production v4 container"
            )

    def test_production_phase12_emits_only_parseable_commands(self):
        import sys

        sys.path.insert(0, str(REPO / "src"))
        import ibcli.commands  # noqa: F401
        from ibcli.parser import expand_line

        lines = _generate("production", phases=[12])
        checked = 0
        for ln in lines:
            if not ln.startswith("configure "):
                continue
            _, error, _ = expand_line(ln)
            assert not error, f"phase 12 emitted an unparseable command:\n{ln}\n{error}"
            checked += 1

        assert checked > 0

    def test_production_dtc_teardown_deletes_built_object_names(self):
        import subprocess
        import sys

        build_lines = _generate("production", phases=[7])
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "smoke" / "teardown.py"),
                "--scale",
                "production",
                "--phases",
                "7",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        teardown_lines = [
            ln for ln in result.stdout.splitlines() if ln.startswith("configure dtc ")
        ]

        build_objects: set[tuple[str, str]] = set()
        for ln in build_lines:
            parts = ln.split()
            if parts[:3] == ["configure", "dtc", "server"] and parts[3] == "add":
                build_objects.add(("server", parts[4]))
            elif parts[:3] == ["configure", "dtc", "pool"] and parts[3] == "add":
                build_objects.add(("pool", parts[4]))
            elif parts[:3] == ["configure", "dtc", "lbdn"] and parts[3] == "add":
                build_objects.add(("lbdn", parts[4]))
            elif parts[:3] == ["configure", "dtc", "topology"] and parts[3] == "add":
                build_objects.add(("topology", parts[4]))
            elif parts[:3] == ["configure", "dtc", "monitor"]:
                if len(parts) >= 6 and parts[4] == "add":
                    build_objects.add((f"monitor {parts[3]}", parts[5]))

        deletes = set()
        for ln in teardown_lines:
            parts = ln.split()
            if parts[:3] == ["configure", "dtc", "server"] and parts[-1] == "delete":
                deletes.add(("server", parts[3]))
            elif parts[:3] == ["configure", "dtc", "pool"] and parts[-1] == "delete":
                deletes.add(("pool", parts[3]))
            elif parts[:3] == ["configure", "dtc", "lbdn"] and parts[-1] == "delete":
                deletes.add(("lbdn", parts[3]))
            elif parts[:3] == ["configure", "dtc", "topology"] and parts[-1] == "delete":
                deletes.add(("topology", parts[3]))
            elif parts[:3] == ["configure", "dtc", "monitor"] and parts[-1] == "delete":
                deletes.add((f"monitor {parts[3]}", parts[4]))

        missing = build_objects - deletes
        assert not missing, f"teardown misses DTC objects: {sorted(missing)[:10]}"


# ---------------------------------------------------------------------------
# Member pre-provisioning: addressing and overrides
#
# The old phase-0 allocator was `10.63.40.{200 + i}`, which produces invalid
# addresses (.256 and up) from the 56th member onward. No scale preset asked
# for more than six members, so it never surfaced until a 200-member run.
# ---------------------------------------------------------------------------


def _shared_mod():
    """Import scripts/smoke/_shared.py the same way build.py does."""
    import sys
    from importlib import import_module

    sys.path.insert(0, str(REPO / "scripts" / "smoke"))
    try:
        return import_module("_shared")
    finally:
        sys.path.pop(0)


def _generate_argv(argv_tail: list[str]) -> list[str]:
    """Run build.main() with an arbitrary argv tail; return emitted lines."""
    import sys

    mod = _load_build()
    old_argv, old_stdout = sys.argv, sys.stdout
    buf = io.StringIO()
    sys.argv = ["build.py", *argv_tail]
    try:
        sys.stdout = buf
        mod.main()
    finally:
        sys.argv, sys.stdout = old_argv, old_stdout
    return [
        ln for ln in buf.getvalue().splitlines() if ln.strip() and not ln.lstrip().startswith("#")
    ]


def test_member_ipv4_stays_in_valid_host_range():
    """Every address must be a real host address, unique, in its own /24."""
    shared = _shared_mod()
    seen = set()
    for i in range(600):
        cidr = shared.member_ipv4(i)
        addr = ipaddress.ip_interface(cidr).ip
        last = int(str(addr).rsplit(".", 1)[1])
        assert 2 <= last <= 254, f"member {i} -> {cidr} is not a host address"
        assert cidr not in seen, f"duplicate address at member {i}: {cidr}"
        seen.add(cidr)


def test_member_gateway_matches_its_own_subnet():
    shared = _shared_mod()
    for i in (0, 100, 252, 253, 500):
        net = shared.member_ipv4(i).split("/")[0].rsplit(".", 1)[0]
        assert shared.member_gateway(i) == f"{net}.1"


def test_two_hundred_members_fit_one_subnet():
    """200 members should not spill across subnets - keeps the lab simple."""
    shared = _shared_mod()
    subnets = {shared.member_ipv4(i).split("/")[0].rsplit(".", 1)[0] for i in range(200)}
    assert len(subnets) == 1


def test_members_override_changes_emitted_count():
    lines = _generate_argv(["--scale", "full", "--members", "200", "--phases", "0"])
    assert sum(1 for ln in lines if "member add" in ln) == 200


def test_members_override_does_not_mutate_shared_scale():
    shared = _shared_mod()
    before = shared.SCALE["full"]["members"]
    _generate_argv(["--scale", "full", "--members", "200", "--phases", "0"])
    assert shared.SCALE["full"]["members"] == before


def test_grid_override_is_used_in_member_commands():
    lines = _generate_argv(["--scale", "tiny", "--grid", "Infoblox", "--phases", "0"])
    joined = "\n".join(lines)
    assert "configure grid Infoblox member add" in joined
    assert "configure grid Migration" not in joined


def test_zero_members_emits_no_member_or_failover_commands():
    """A grid that can't take members must still build DNS/DHCP cleanly."""
    lines = _generate_argv(["--scale", "full", "--members", "0", "--phases", "0,2"])
    joined = "\n".join(lines)
    assert "member add" not in joined
    # Failover pairs need two members each; with none there are no pairs.
    assert "network failover add" not in joined


# ---------------------------------------------------------------------------
# Phase 0 member variants
#
# Members cycle through interface shapes so a build exercises VLAN tagging,
# MGMT ports, HA pairs and port redundancy - not just plain members. The
# address allocations below are the ones a live NIOS 9.x grid accepts;
# several near-misses are rejected and are noted per test.
# ---------------------------------------------------------------------------


def _member_lines(n: int) -> list[str]:
    return [
        ln
        for ln in _generate_argv(["--scale", "full", "--members", str(n), "--phases", "0"])
        if "member add" in ln
    ]


def test_all_variants_appear_in_a_full_cycle():
    shared = _shared_mod()
    lines = _member_lines(len(shared.MEMBER_VARIANTS))
    joined = "\n".join(lines)
    assert "vlan_id=" in joined
    assert "mgmt_ipaddress=" in joined
    assert "router_id=" in joined and "ha_node=" in joined
    assert "port_redundancy=true" in joined


def test_ha_members_keep_node_addresses_in_the_vip_subnet():
    """NIOS: 'Send HA and Grid communication requires valid LAN1 IPv4
    addresses' unless each node's LAN1 shares the VIP's subnet."""
    import ipaddress as _ip

    shared = _shared_mod()
    for i in range(0, 400):
        if shared.member_variant(i) != "ha":
            continue
        a = shared.member_ha_addrs(i)
        net = _ip.ip_network(a["vip"], strict=False)
        for key in ("gateway", "node1_lan1", "node1_ha", "node2_lan1", "node2_ha"):
            assert _ip.ip_address(a[key]) in net, f"member {i}: {key} outside {net}"


def test_ha_node_addresses_are_unique_within_a_member():
    shared = _shared_mod()
    for i in range(0, 400):
        if shared.member_variant(i) != "ha":
            continue
        a = shared.member_ha_addrs(i)
        addrs = [a[k] for k in ("node1_lan1", "node1_ha", "node2_lan1", "node2_ha")]
        assert len(set(addrs)) == 4, f"member {i} reuses an address: {addrs}"


def test_ha_node_mgmt_shares_the_mgmt_gateway_subnet():
    """NIOS: 'The gateway address <gw> must be in the same subnet as the IP
    address <ip> for MGMT' - both nodes must sit beside the gateway."""
    import ipaddress as _ip

    shared = _shared_mod()
    for i in range(0, 400):
        if shared.member_variant(i) != "ha":
            continue
        a = shared.member_ha_addrs(i)
        gw = shared.member_mgmt_gateway(i)
        net = _ip.ip_network(f"{gw}/24", strict=False)
        for key in ("node1_mgmt", "node2_mgmt"):
            assert _ip.ip_address(a[key]) in net, f"member {i}: {key} not in {net}"
        assert a["node1_mgmt"] != a["node2_mgmt"]


def test_mgmt_addresses_never_collide_across_members():
    shared = _shared_mod()
    seen: set[str] = set()
    for i in range(400):
        own = shared.member_mgmt_ipv4(i).split("/")[0]
        assert own not in seen, f"member {i} reuses MGMT {own}"
        seen.add(own)


def test_port_redundancy_members_get_no_lan2_address():
    """LAN2 is the standby for LAN1 under port redundancy - NIOS drops any
    address given to it, so the harness must not emit one."""
    shared = _shared_mod()
    n = len(shared.MEMBER_VARIANTS) * 2
    for ln in _member_lines(n):
        if "port_redundancy=true" in ln:
            assert "lan2_ipaddress=" not in ln


def test_vlan_ids_stay_in_the_valid_802_1q_range():
    shared = _shared_mod()
    for i in range(0, 4000):
        assert 1 <= shared.member_vlan_id(i) <= 4094


def test_router_ids_stay_in_the_vrrp_range():
    shared = _shared_mod()
    for i in range(0, 4000):
        assert 1 <= shared.member_router_id(i) <= 255


def test_teardown_warns_when_members_torn_down_alone():
    """Phase 0 alone cannot succeed - NS groups (1) and DHCP failovers (2)
    hold references NIOS refuses to delete members through."""
    import subprocess
    import sys as _sys

    out = subprocess.run(
        [
            _sys.executable,
            str(REPO / "scripts" / "smoke" / "teardown.py"),
            "--scale",
            "full",
            "--members",
            "3",
            "--phases",
            "0",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO / "scripts" / "smoke"),
    )
    assert "WARNING" in out.stderr
    assert "NS groups" in out.stderr and "failover" in out.stderr


def test_teardown_is_quiet_for_a_full_run():
    import subprocess
    import sys as _sys

    out = subprocess.run(
        [
            _sys.executable,
            str(REPO / "scripts" / "smoke" / "teardown.py"),
            "--scale",
            "full",
            "--members",
            "3",
            "--phases",
            "0,1,2",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO / "scripts" / "smoke"),
    )
    assert "WARNING" not in out.stderr
