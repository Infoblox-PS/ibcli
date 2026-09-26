#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Verify a smoke-build run by counting objects on the grid and comparing
against the expected counts for the selected scale.

Uses direct WAPI calls (via curl) filtered by either the Smoke EA (for
object types that support EAs) or the smoke-* name prefix. Exits 0 if all
checks pass, 1 otherwise.

Usage:
    python3 scripts/smoke/verify.py \\
        --host 192.0.2.39 --user admin --password '<password>' \\
        --scale full --tag v1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode

from _shared import (
    SCALE,
)


def wapi_count(
    host: str, user: str, password: str, object_type: str, query: str = "", max_results: int = 1000
) -> int:
    """GET /wapi/v2.14/<object>?<query> and return the number of rows returned.

    `max_results` is sized to the caller's expected count plus slack. Larger
    scales ask for more; small expected populations keep the response small.
    """
    total = 0
    page_id: str | None = None

    while True:
        params = {
            "_max_results": str(max_results),
            "_paging": "1",
            "_return_as_object": "1",
        }
        if page_id:
            params["_page_id"] = page_id

        q = f"{query}{'&' if query else ''}{urlencode(params)}"
        url = f"https://{host}/wapi/v2.14/{object_type}?{q}"
        try:
            raw = subprocess.check_output(
                ["curl", "-sk", "-u", f"{user}:{password}", url],
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
        except subprocess.CalledProcessError:
            return -1
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return -1

        # Older WAPI/object combinations may ignore _return_as_object and
        # return a plain list. Count it and stop.
        if isinstance(data, list):
            return total + len(data)
        if not isinstance(data, dict) or not isinstance(data.get("result"), list):
            return -1

        total += len(data["result"])
        page_id = data.get("next_page_id")
        if not page_id:
            return total


def check(label: str, actual: int, expected: int, slack: int = 0) -> bool:
    """Pass if actual is within [expected - slack, ∞) - smoke builds may pick
    up extra objects from earlier runs, so we only assert a lower bound."""
    if actual < 0:
        print(f"  FAIL  {label:45s}  query failed")
        return False
    if actual < expected - slack:
        print(f"  FAIL  {label:45s}  got {actual}, expected ≥ {expected}")
        return False
    print(f"  ok    {label:45s}  {actual} (expected ≥ {expected})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--scale", choices=list(SCALE), default="full")
    ap.add_argument("--tag", default="yes")
    ap.add_argument(
        "--members",
        type=int,
        default=None,
        help="Override the scale's expected member count, to "
        "match a build run with the same --members value.",
    )
    args = ap.parse_args()

    # Copy so an override never mutates the shared SCALE table.
    p = dict(SCALE[args.scale])
    if args.members is not None:
        if args.members < 0:
            ap.error("--members must be >= 0")
        p["members"] = args.members
    # EA-filter for object types that support it (networks tagged with the
    # Smoke EA at add time). Name-prefix filter for everything else.
    ea = f"*Smoke={quote(args.tag)}"
    name_prefix = "name~=smoke-"

    # Queue up count jobs, execute them in parallel, collect results.
    jobs: list[tuple[str, str, str, int]] = []

    def count(label: str, obj: str, query: str, expected: int) -> None:
        jobs.append((label, obj, query, expected))

    # Phase 0: Members.
    count("members", "member", "host_name~=smoke-mbr", p["members"])

    # Phase 1: Infrastructure.
    count("views", "view", name_prefix, p["views"])
    count("nsgroups", "nsgroup", name_prefix, p["nsgroups"])
    count("acls", "namedacl", name_prefix, p["acls"])
    count("EA defs", "extensibleattributedef", "name~=smoke-ea", p["eas"])

    # Phase 10: DHCP extras.
    count("option spaces", "dhcpoptionspace", name_prefix, p["option_spaces"])
    count("filter option", "filteroption", "name~=smoke-filt-opt", p["filters_option"])
    count("filter nac", "filternac", "name~=smoke-filt-nac", p["filters_nac"])
    count("filter ipv6option", "ipv6filteroption", "name~=smoke-filt-v6o", p["filters_ipv6option"])
    count("filter relayagent", "filterrelayagent", "name~=smoke-filt-ra", p["filters_relayagent"])
    count("network templates", "networktemplate", "name~=smoke-nettmpl", p["net_templates"])
    count("range templates", "rangetemplate", "name~=smoke-rangetmpl", p["range_templates"])

    # Phase 2: DHCP.
    count("networks v4", "network", ea, p["networks_v4"])
    count("networks v6", "ipv6network", ea, p["networks_v6"])
    count("ranges", "range", "", p["networks_v4"] * p["ranges_per_net"])
    count("fixed", "fixedaddress", "", p["networks_v4"] * p["fixed_per_net"])
    # dhcpfailover doesn't support name~=; the listing is short so pull all
    # and count smoke-prefixed entries client-side.
    # NOTE: on a grid that already has a `fo-group1` covering the same DHCP
    # pair as smoke-fo-00, NIOS silently skips the duplicate. Keep slack=all
    # so the verify isn't blocked by that pre-existing state.
    count("failovers", "dhcpfailover", "", 0)  # just ensure object listable

    # Phase 3: DNS zones.
    count("forward zones", "zone_auth", "fqdn~=smoke-zone", p["fwd_zones"])
    # Reverse zones are indexed by their CIDR fqdn (e.g. "10.100.0.0/24"),
    # not their in-addr.arpa form. Filter by zone_format + our CIDR prefix.
    count("reverse zones", "zone_auth", "zone_format=IPV4&fqdn~=10.100.", p["rev_zones"])

    # Phase 11: RFC 6303 / RFC 6598 locally-served reverse zones.
    # Check the well-known anchor zones for each family rather than counting
    # every zone - the RFC list is fixed and independent of scale.
    #
    # Two NIOS behaviours shape these queries. First, NIOS normalises an arpa
    # zone name to its CIDR on create, so `10.in-addr.arpa` comes back as
    # `10.0.0.0/8` and searching by the arpa spelling never matches. Second,
    # combining `zone_format=` with an arpa `fqdn=` makes NIOS 500 with
    # "AdmConError: None (list index out of range)" - so filter on the
    # canonical fqdn alone, which is already unambiguous.
    count("RFC 6303 v4 reverse zones", "zone_auth", "fqdn=10.0.0.0/8", 1)
    count("RFC 6303 v6 reverse zones", "zone_auth", "fqdn=fd00::/8", 1)
    count("RFC 6598 CGN reverse zones", "zone_auth", "fqdn=100.64.0.0/16", 1)

    # Phase 4: DNS records - sample two types.
    def s(pct: int) -> int:
        return max(1, p["records_per_zone"] * pct // 100)

    count("A records", "record:a", "name~=smoke-zone", p["fwd_zones"] * s(40))
    count("AAAA records", "record:aaaa", "name~=smoke-zone", p["fwd_zones"] * s(20))
    # PTR coverage: one per A (v4), one per AAAA (v6), one per host (v4).
    # PTRs land in the RFC 6303 umbrella zones 10.in-addr.arpa (v4) /
    # 8.b.d.0.1.0.0.2.ip6.arpa (v6). Use ptrdname~= rather than zone~= so
    # the filter survives whatever reverse zone NIOS routes each PTR to.
    # Combine v4 + v6 PTRs in a single count: both answer the same
    # record:ptr endpoint filtered by ptrdname.
    expected_ptrs = (
        p["fwd_zones"] * s(40)  # v4 PTRs from A records
        + p["fwd_zones"] * s(20)  # v6 PTRs from AAAA records
        + p["host_records"]  # v4 PTRs from hosts
    )
    count("PTR records", "record:ptr", "ptrdname~=smoke-zone", expected_ptrs)
    count("CNAME records", "record:cname", "name~=smoke-zone", p["fwd_zones"] * s(12))
    count("MX records", "record:mx", "name~=smoke-zone", p["fwd_zones"] * s(6))
    count("TXT records", "record:txt", "name~=smoke-zone", p["fwd_zones"] * s(12))

    # Phase 5: Hosts.
    count("host records", "record:host", "name~=shost", p["host_records"])
    count("shared rec grp", "sharedrecordgroup", "name~=smoke-srg", p["shared_rec_groups"])

    # Phase 6: RPZ.
    count("RPZ zones", "zone_rp", "fqdn~=smoke-rpz", p["rpz_zones"])

    # Phase 7: DTC.
    count("DTC servers", "dtc:server", "name~=smoke-srv", p["dtc_servers"])
    count("DTC pools", "dtc:pool", "name~=smoke-pool", p["dtc_pools"])
    count("DTC LBDNs", "dtc:lbdn", "name~=smoke-lbdn", p["dtc_lbdns"])
    count("DTC topologies", "dtc:topology", "name~=smoke-topo", p.get("dtc_topologies", 0))

    # Phase 8: Admin.
    count("admin users", "adminuser", "name~=smoke-user", p["admin_users"])
    count("admin groups", "admingroup", "name~=smoke-group", p["admin_groups"])
    count("admin roles", "adminrole", "name~=smoke-role", p["admin_roles"])

    # Phase 9: Notifications.
    count("notify endpoints", "notification:rest:endpoint", "name~=smoke-ep", p["notify_endpoints"])
    # Rules intentionally skipped - creating a notification rule programmatically
    # requires a non-empty expression_list whose shape depends on event_type;
    # that's beyond the smoke-test scope. See scripts/smoke/build.py.

    # Phase 12: Production extras. Each count() is a no-op when the scale's
    # count is 0, so tiny/small/full quietly skip them.
    def _maybe(label: str, obj: str, query: str, key: str) -> None:
        if p.get(key, 0) > 0:
            count(label, obj, query, p[key])

    _maybe(
        "network containers v4", "networkcontainer", "network_view=default", "network_containers_v4"
    )
    _maybe(
        "network containers v6",
        "ipv6networkcontainer",
        "network_view=default",
        "network_containers_v6",
    )
    _maybe("network views", "networkview", "name~=smoke-nv", "network_views")
    _maybe("VLAN views", "vlanview", "name~=smoke-vlanview", "vlan_views")
    _maybe("roaming hosts", "roaminghost", "name~=smoke-roam", "roaming_hosts")
    _maybe("bulk hosts", "bulkhost", "prefix~=smoke-bulk", "bulk_hosts")
    _maybe("custom v4 optiondefs", "dhcpoptiondefinition", "name~=smoke-opt-v4", "optiondefs_v4")
    _maybe(
        "custom v6 optiondefs", "ipv6dhcpoptiondefinition", "name~=smoke-opt-v6", "optiondefs_v6"
    )
    _maybe("fingerprint defs", "fingerprint", "name~=smoke-fp", "fingerprint_defs")
    _maybe("record-name policies", "record_name_policy", "name~=smoke-rnp", "record_name_policies")
    _maybe("hostname policies", "hostnamerewritepolicy", "name~=smoke-hnp", "hostname_policies")
    _maybe("BFD templates", "bfdtemplate", "name~=smoke-bfd", "bfd_templates")
    _maybe("NAT groups", "natgroup", "name~=smoke-nat", "nat_groups")
    _maybe("RIR organizations", "rir:organization", "name~=smoke-rir", "rir_orgs")
    _maybe("upgrade groups", "upgradegroup", "name~=smoke-ug", "upgrade_groups")
    # Extra record types created in phase 12.
    extras = p.get("dname_records_per_zone", 0)
    if extras and p.get("fwd_zones", 0):
        expected = extras * p["fwd_zones"]
        count("DNAME records", "record:dname", "name~=smoke-zone", expected)

    print(f"\nVerifying {len(jobs)} object types against scale={args.scale}:\n")

    def run(job: tuple[str, str, str, int]) -> tuple[str, int, int]:
        label, obj, query, expected = job
        # Ask NIOS for only as many rows as we need to prove the lower bound,
        # plus slack for prior leftover objects. Minimum page size of 128
        # keeps the per-request overhead dominant-free; the max cap keeps
        # production-scale verifies from pulling ~750K row responses.
        max_results = max(128, min(50000, expected * 3))
        actual = wapi_count(
            args.host, args.user, args.password, obj, query, max_results=max_results
        )
        return (label, actual, expected)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, jobs))

    passed = sum(1 for r in results if check(*r))
    total = len(results)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
