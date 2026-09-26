#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Generate a teardown .ibcli script that removes everything a smoke-build
run created, in dependency-safe reverse order.

Usage:
    python3 scripts/smoke/teardown.py --scale full > smoke-teardown.ibcli

Must be called with the **same --scale** that was used for the build, so the
emitted delete commands target the same name range. The --tag is irrelevant
for teardown because deletes key on the smoke-* name prefix, not on EAs.
"""

from __future__ import annotations

import argparse
import sys

from _shared import (
    GRID_NAME,
    RFC_LOCAL_ZONES,
    SCALE,
    SMOKE_ADMIN_GROUP,
    bulkhost_name,
    dtc_lbdn_name,
    dtc_monitor_kind,
    dtc_monitor_name,
    dtc_pool_name,
    dtc_server_name,
    dtc_topology_name,
    failover_name,
    fwd_zone_fqdn,
    member_fqdn,
    network_view_name,
    rev_zone_fqdn,
    roaming_host_name,
    v4_container_cidr,
    v4_network_cidr,
    v6_container_cidr,
    v6_network_cidr,
    vlan_view_name,
)


def emit(*lines: str) -> None:
    for ln in lines:
        print(ln)


def header(title: str) -> None:
    print()
    print("# " + "-" * 74)
    print(f"# {title}")
    print("# " + "-" * 74)


# ---------------------------------------------------------------------------
# Teardown is build.py in reverse. Each function mirrors its counterpart.
# ---------------------------------------------------------------------------


def td_notifications(p: dict) -> None:
    header("Reverse PHASE 9 - Notifications")
    for i in range(p["notify_rules"]):
        emit(f"configure notification rule smoke-rule-{i:02d} delete")
    for i in range(p["notify_endpoints"]):
        emit(f"configure notification endpoint smoke-ep-{i:02d} delete")


def td_admin(p: dict) -> None:
    header("Reverse PHASE 8 - Admin")
    # Delete users first (they reference groups).
    for i in range(p["admin_users"]):
        emit(f"configure admin user smoke-user-{i:02d} delete")
    # Then the smoke groups, including the base group users referenced.
    for i in range(p["admin_groups"]):
        emit(f"configure admin group smoke-group-{i:02d} delete")
    emit(f"configure admin group {SMOKE_ADMIN_GROUP} delete")
    for i in range(p["admin_roles"]):
        emit(f"configure admin role smoke-role-{i:02d} delete")


def td_dtc(p: dict) -> None:
    header("Reverse PHASE 7 - DTC")
    for i in range(p.get("dtc_topologies", 0)):
        emit(f"configure dtc topology {dtc_topology_name(i)} delete")
    for i in range(p["dtc_lbdns"]):
        emit(f"configure dtc lbdn {dtc_lbdn_name(i)} delete")
    for i in range(p["dtc_pools"]):
        emit(f"configure dtc pool {dtc_pool_name(i)} delete")
    for i in range(p["dtc_servers"]):
        emit(f"configure dtc server {dtc_server_name(i)} delete")
    for i in range(p["dtc_monitors"]):
        proto = dtc_monitor_kind(i)
        emit(f"configure dtc monitor {proto} {dtc_monitor_name(i)} delete")


def td_rpz(p: dict) -> None:
    header("Reverse PHASE 6 - RPZ")
    # Deleting an RPZ zone cascades to its records, so no per-record deletes.
    for i in range(p["rpz_zones"]):
        emit(f"configure rpz zone smoke-rpz{i:02d}.example.com delete")


def td_hosts(p: dict) -> None:
    header("Reverse PHASE 5 - Hosts, shared records")
    # Deleting the shared_record_group cascades to its shared records, so
    # we skip per-record deletes (WAPI refuses to search shared_record by
    # shared_record_group anyway).
    for g in range(p["shared_rec_groups"]):
        grp = f"smoke-srg-{g:02d}"
        emit(f"configure shared_record_group {grp} delete")
    # Host records - deleted by zone cascade in td_dns_zones().


def td_dns_records(p: dict) -> None:
    """DNS records get deleted by the zone-cascade in td_dns_zones().

    NIOS delete of a zone removes all of its records atomically, so
    we don't emit per-record deletes here - much faster and safer.
    """
    header("Reverse PHASE 4 - DNS records (cascade via zone delete)")
    emit("# (no per-record deletes - handled by zone delete cascade below)")


def td_dns_zones(p: dict) -> None:
    header("Reverse PHASE 3 - DNS zones")
    for i in range(p["fwd_zones"]):
        emit(f"configure zone {fwd_zone_fqdn(i)} delete")
    for i in range(p["rev_zones"]):
        emit(f"configure zone {rev_zone_fqdn(i)} delete")


def td_dhcp(p: dict) -> None:
    header("Reverse PHASE 2 - DHCP")
    for i in range(p["option_filters"]):
        emit(f"configure network macfilter delete smoke-macfilt-{i:02d}")
    for i in range(p["networks_v6"]):
        emit(f"configure network {v6_network_cidr(i)} delete")
    for i in range(p["networks_v4"]):
        # Network delete cascades to its ranges and fixed addresses.
        emit(f"configure network {v4_network_cidr(i)} delete")
    for i in range(p.get("network_containers_v6", 0)):
        emit(f"configure network {v6_container_cidr(i)} delete")
    for i in range(p.get("network_containers_v4", 0)):
        emit(f"configure network {v4_container_cidr(i)} delete")
    for i in range(p["failovers"]):
        emit(f"configure network failover delete {failover_name(i)}")


def td_infrastructure(p: dict) -> None:
    header("Reverse PHASE 1 - Infrastructure")
    for i in range(p["acls"]):
        emit(f"configure acl smoke-acl-{i:02d} delete")
    for i in range(p["nsgroups"]):
        emit(f"configure nsgroup smoke-nsg-{i:02d} delete")
    for i in range(p["views"]):
        emit(f"configure view smoke-view-{i:02d} delete")
    for i in range(p["eas"]):
        emit(f"configure grid attribute smoke-ea-{i:03d} delete")
    # The Smoke EA itself - delete last (it's referenced by other objects).
    emit("configure grid attribute Smoke delete")


def td_members(p: dict) -> None:
    header("Reverse PHASE 0 - Members")
    # Members must be removed AFTER anything that references them (NS groups,
    # failovers, network-member bindings). Runs last in the teardown order.
    for i in range(p["members"]):
        emit(f"configure grid {GRID_NAME} member {member_fqdn(i)} delete")


def td_rfc_local_zones(p: dict) -> None:
    """Reverse phase 11 - delete the RFC 6303 / RFC 6598 reverse zones.

    These are fully-qualified .arpa names with no smoke- prefix, so the
    teardown deletes each one explicitly. Missing zones surface as
    idempotent-skip when the teardown is driven with `ibcli -i`.
    """
    _ = p
    header("Reverse PHASE 11 - RFC 6303 + RFC 6598 reverse zones")
    for fqdn in RFC_LOCAL_ZONES:
        emit(f"configure zone {fqdn} delete")


def td_dhcp_extras(p: dict) -> None:
    header("Reverse PHASE 10 - DHCP extras")
    for i in range(p["range_templates"]):
        emit(f"configure template range delete smoke-rangetmpl-{i:02d}")
    for i in range(p["net_templates"]):
        emit(f"configure template network smoke-nettmpl-{i:02d} delete")
    for i in range(p["filters_relayagent"]):
        emit(f"configure filter relayagent smoke-filt-ra-{i:02d} delete")
    for i in range(p["filters_ipv6option"]):
        emit(f"configure filter ipv6option smoke-filt-v6o-{i:02d} delete")
    for i in range(p["filters_nac"]):
        emit(f"configure filter nac smoke-filt-nac-{i:02d} delete")
    for i in range(p["filters_option"]):
        emit(f"configure filter option smoke-filt-opt-{i:02d} delete")
    for i in range(p["option_spaces"]):
        emit(f"configure option_space smoke-optspace-{i:02d} delete")


def td_production_extras(p: dict) -> None:
    """Mirror of phase 12. A no-op for tiny/small/full because each count
    defaults to 0 at those scales."""
    if not any(
        p.get(k, 0)
        for k in (
            "network_views",
            "vlan_views",
            "roaming_hosts",
            "bulk_hosts",
            "optiondefs_v4",
            "optiondefs_v6",
            "fingerprint_defs",
            "record_name_policies",
            "hostname_policies",
            "bfd_templates",
            "nat_groups",
            "rir_orgs",
            "upgrade_groups",
        )
    ):
        return
    header("Reverse PHASE 12 - Production extras")

    # Upgrade-related, RIR, infra - independent; delete first.
    for i in range(p.get("upgrade_groups", 0)):
        emit(f"configure upgrade_group smoke-ug-{i:02d} delete")
    for i in range(p.get("rir_orgs", 0)):
        emit(f"configure rir_organization smoke-rir-{i:02d} delete")
    for i in range(p.get("nat_groups", 0)):
        emit(f"configure nat_group smoke-nat-{i:02d} delete")
    for i in range(p.get("bfd_templates", 0)):
        emit(f"configure bfd_template smoke-bfd-{i:02d} delete")
    for i in range(p.get("hostname_policies", 0)):
        emit(f"configure hostname_policy smoke-hnp-{i:02d} delete")
    for i in range(p.get("record_name_policies", 0)):
        emit(f"configure record_name_policy smoke-rnp-{i:02d} delete")
    for i in range(p.get("fingerprint_defs", 0)):
        emit(f"configure fingerprint smoke-fp-{i:02d} delete")
    # Custom option defs must go before the option-spaces they reference
    # (phase 10 teardown) - TEARDOWN_PHASES orders 12 before 10 accordingly.
    for i in range(p.get("optiondefs_v6", 0)):
        emit(f"configure ipv6optiondef smoke-opt-v6-{i:02d} delete")
    for i in range(p.get("optiondefs_v4", 0)):
        emit(f"configure optiondef smoke-opt-v4-{i:02d} delete")
    # Bulk hosts must go before the zones they attach to (phase 3).
    for i in range(p.get("bulk_hosts", 0)):
        emit(f"configure bulkhost {bulkhost_name(i)} delete")
    # Roaming hosts - independent of networks, delete anytime.
    for i in range(p.get("roaming_hosts", 0)):
        emit(f"configure roaming_host {roaming_host_name(i)} delete")
    # VLAN hierarchy - vlans → vlan_ranges → vlan_views.
    for i in range(p.get("vlan_views", 0)):
        vv = vlan_view_name(i)
        for v in range(p.get("vlans_per_view", 0)):
            emit(f"configure vlan smoke-vlan-{i:02d}-{v:04d} delete")
        emit(f"configure vlan_range {vv}-range delete")
        emit(f"configure vlan_view {vv} delete")
    # Extra network views (separate from DNS views in phase 1).
    for i in range(p.get("network_views", 0)):
        emit(f"configure network_view {network_view_name(i)} delete")


# Reverse-order dispatch. Members come dead last so dependent objects
# (failovers, nsgroups, network-member bindings) have already released them.
TEARDOWN_PHASES = [
    (9, td_notifications),
    (8, td_admin),
    (7, td_dtc),
    (6, td_rpz),
    (5, td_hosts),
    (4, td_dns_records),
    (12, td_production_extras),
    (11, td_rfc_local_zones),
    (3, td_dns_zones),
    (10, td_dhcp_extras),
    (2, td_dhcp),
    (1, td_infrastructure),
    (0, td_members),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scale", choices=list(SCALE), default="full")
    ap.add_argument(
        "--phases",
        default="0,1,2,3,4,5,6,7,8,9,10,11,12",
        help="Phases to tear down. Runs in reverse-dependency "
        "order regardless of the order listed here.",
    )
    ap.add_argument(
        "--members",
        type=int,
        default=None,
        help="Override the scale's member count. Must match the "
        "value the build used, or pre-provisioned members "
        "are left behind.",
    )
    ap.add_argument(
        "--grid",
        default=None,
        help="Grid name for `configure grid <name> member "
        "delete`. Defaults to IBCLI_SMOKE_GRID or "
        "'Migration'.",
    )
    args = ap.parse_args()

    wanted = {int(x) for x in args.phases.split(",") if x.strip()}

    # Members can't be deleted while anything still points at them. NIOS
    # refuses with e.g. "cannot be removed because it is the DHCP failover
    # primary in <fo>" (phase 2) or "is a primary server for NS Group <g>"
    # (phase 1). The full teardown order already handles this - tearing down
    # phase 0 on its own does not.
    if 0 in wanted and not {1, 2} <= wanted:
        missing = sorted({1, 2} - wanted)
        print(
            "# WARNING: phase 0 (members) without phase(s) "
            f"{', '.join(map(str, missing))} - NS groups (1) and DHCP "
            "failover associations (2) hold references that block member "
            "deletion. Add them or member deletes will fail.",
            file=sys.stderr,
        )
    # Copy so an override never mutates the shared SCALE table.
    params = dict(SCALE[args.scale])
    if args.members is not None:
        # Same guard as build.py: a negative count silently empties the
        # member phase, which looks like a clean teardown while leaving every
        # pre-provisioned member behind.
        if args.members < 0:
            ap.error("--members must be >= 0")
        params["members"] = args.members
    if args.grid:
        import _shared

        _shared.GRID_NAME = args.grid
        globals()["GRID_NAME"] = args.grid

    emit("# ibcli smoke-test teardown script")
    emit(f"# scale={args.scale}  phases={sorted(wanted)}")
    emit("# Run with: ibcli -i -s <host> -u <user> -p <pw> -k smoke-teardown.ibcli")
    emit("# Order: reverse-dependency (notifications → admin → DTC → ... → infra)")

    for n, fn in TEARDOWN_PHASES:
        if n in wanted:
            fn(params)


if __name__ == "__main__":
    main()
