#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Generate a comprehensive smoke-test .ibcli script.

Produces roughly 10,000 objects across 9 phases exercising the full CRUD
surface of ibcli. All object names are prefixed ``smoke-`` so teardown.py
can target them safely without consulting EAs.

Usage:
    python3 scripts/smoke/build.py \\
        --tag v1 \\
        --scale full \\
        --phases 1,2,3,4,5,6,7,8,9 \\
        > smoke-build.ibcli

Scales:
    tiny        -    ~100 objects, for plumbing checks
    small       -  ~1,000 objects, for quick smoke runs
    full        - ~10,000 objects, the "real" smoke test
    production  - ~500,000+ objects with 250K+ DNS records and 250K+
                  DHCP fixed addresses, every object type ibcli can
                  create. TAKE A GRID BACKUP FIRST - see
                  scripts/smoke/backup.py. Build runs for several hours
                  against a live grid.

Individual phases can be run by passing a comma-separated subset to
``--phases``.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys

from _shared import (
    GRID_NAME,
    RFC_LOCAL_ZONES,
    SCALE,
    SMOKE_ADMIN_GROUP,
    bulkhost_name,
    dtc_label_name,
    dtc_lbdn_name,
    dtc_monitor_kind,
    dtc_monitor_name,
    dtc_pool_name,
    dtc_server_name,
    dtc_topology_name,
    failover_name,
    fwd_zone_fqdn,
    member_fqdn,
    member_gateway,
    member_ha_addrs,
    member_ipv4,
    member_ipv6,
    member_ipv6_gateway,
    member_mgmt_gateway,
    member_mgmt_ipv4,
    member_router_id,
    member_variant,
    member_vlan_id,
    network_view_name,
    rev_zone_fqdn,
    roaming_host_name,
    smoke_members,
    v4_container_cidr,
    v4_network_cidr,
    v6_container_cidr,
    v6_network_cidr,
    vlan_view_name,
)


class Builder:
    """Emits ibcli commands. Objects where the grammar accepts ``set`` at
    add time get tagged with ``set Smoke <tag>``; others rely on their
    ``smoke-`` name prefix for teardown filtering."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.ea = f"set Smoke {tag}"  # append only to add-commands that accept it

    def emit(self, *lines: str) -> None:
        for line in lines:
            print(line)

    def header(self, title: str, count: int | str = "") -> None:
        bar = "# " + "-" * 74
        count_s = f"  ({count} objects)" if count != "" else ""
        self.emit("", bar, f"# {title}{count_s}", bar)


# ===========================================================================
# Phases
# ===========================================================================


def phase0_members(b: Builder, p: dict) -> None:
    """Pre-provision grid members. Uses a dedicated IP subnet (10.63.40.x)
    so smoke members don't collide with the main `ibdns*`/`ibdhcp*` ones.
    """
    n = p["members"]
    b.header(f"PHASE 0 - Members (pre-provisioned on {GRID_NAME})", n)

    # Cycle through interface shapes so a build exercises plain members,
    # VLAN-tagged LAN1, a MGMT port, HA pairs and port redundancy. `hwtype`
    # is the only hardware_info field every NIOS version accepts - the CLI
    # drops the rest against a grid that rejects them.
    lic = "license=dns license=dhcp license=nios license=enterprise"
    for i in range(n):
        fqdn = member_fqdn(i)
        variant = member_variant(i)

        if variant == "ha":
            a = member_ha_addrs(i)
            b.emit(
                f"configure grid {GRID_NAME} member add {fqdn} "
                f"ipaddress={a['vip']} gateway={a['gateway']} "
                f"vlan_id={member_vlan_id(i)} "
                f"router_id={member_router_id(i)} "
                f"ha_node={a['node1_lan1']},{a['node1_ha']},{a['node1_mgmt']} "
                f"ha_node={a['node2_lan1']},{a['node2_ha']},{a['node2_mgmt']} "
                f"mgmt_ipaddress={member_mgmt_ipv4(i)} "
                f"mgmt_gateway={member_mgmt_gateway(i)} "
                f"master_candidate=true "
                f"platform=VNIOS node=IB-V1425 node=IB-V1425 {lic}"
            )
            continue

        parts = [
            f"configure grid {GRID_NAME} member add {fqdn}",
            f"ipaddress={member_ipv4(i)}",
            f"gateway={member_gateway(i)}",
            f"ipv6addr={member_ipv6(i)}",
            f"ipv6gateway={member_ipv6_gateway(i)}",
        ]
        if variant == "vlan":
            parts.append(f"vlan_id={member_vlan_id(i)}")
        elif variant == "mgmt":
            parts += [
                f"mgmt_ipaddress={member_mgmt_ipv4(i)}",
                f"mgmt_gateway={member_mgmt_gateway(i)}",
            ]
        elif variant == "portred":
            # LAN2 is the standby for LAN1, so it takes no address.
            parts += ["port_redundancy=true", "port_redundancy_primary=true"]
        parts += ["platform=VNIOS", "hwtype=IB-V1425", lic]
        b.emit(" ".join(parts))


def phase1_infrastructure(b: Builder, p: dict) -> None:
    """Views, NS groups, ACLs, EA definitions."""
    n = p["views"] + p["nsgroups"] + p["acls"] + p["eas"] + 1
    b.header("PHASE 1 - Infrastructure (views, nsgroups, ACLs, EAs)", n)

    # Base Smoke EA - referenced by add-commands that set EAs.
    b.emit("configure grid attribute add Smoke type string")

    # Additional EA definitions across supported types.
    ea_types = ["string", "integer", "email", "url", "date"]
    for i in range(p["eas"]):
        t = ea_types[i % len(ea_types)]
        b.emit(f"configure grid attribute add smoke-ea-{i:03d} type {t}")

    # Views (grammar accepts only the name - no trailing set/comment).
    for i in range(p["views"]):
        b.emit(f"configure view add smoke-view-{i:02d}")

    # NS groups - primary= references one of the smoke-created members. If
    # phase 0 wasn't run we fall back to the grid master host, which every
    # NIOS grid has.
    mbrs = smoke_members(p["members"]) or ["infoblox.localdomain"]
    for i in range(p["nsgroups"]):
        b.emit(f"configure nsgroup add smoke-nsg-{i:02d} primary={mbrs[i % len(mbrs)]}")

    # ACLs - access_list= is required so the ACL has at least one entry.
    for i in range(p["acls"]):
        b.emit(f"configure acl add smoke-acl-{i:02d} access_list=10.{i % 256}.0.0/16")


def phase2_dhcp(b: Builder, p: dict) -> None:
    """Networks, ranges, fixed addresses, filters, failovers."""
    v4, v6 = p["networks_v4"], p["networks_v6"]
    total = (
        p.get("network_containers_v4", 0)
        + p.get("network_containers_v6", 0)
        + (v4 + v6)
        + v4 * p["ranges_per_net"]
        + v4 * p["fixed_per_net"]
        + p["option_filters"]
        + p["failovers"]
    )
    b.header("PHASE 2 - DHCP (networks, ranges, fixed, filters, failovers)", total)

    # Failover peers - each association needs a unique primary+secondary
    # pair. With `m` smoke members we can make at most floor(m/2) distinct
    # pairs; cap p["failovers"] accordingly.
    mbrs = smoke_members(p["members"])
    max_fo = len(mbrs) // 2
    for i in range(min(p["failovers"], max_fo)):
        primary = mbrs[2 * i]
        secondary = mbrs[2 * i + 1]
        b.emit(
            f"configure network failover add {failover_name(i)} "
            f"primary {primary} secondary {secondary}"
        )

    # IPv4 containers need to exist before their child networks. Smaller scales
    # keep the count at 0, so this is production-only.
    for i in range(p.get("network_containers_v4", 0)):
        b.emit(f"configure network add {v4_container_cidr(i)} {b.ea}")
    for i in range(p.get("network_containers_v6", 0)):
        b.emit(f"configure network add {v6_container_cidr(i)} {b.ea}")

    # IPv4 networks + ranges + fixed.
    for i in range(v4):
        cidr = v4_network_cidr(i)
        net = ipaddress.ip_network(cidr, strict=False)
        # Derive the dotted prefix from the CIDR itself so range/fixed IPs land
        # inside it without duplicating the network arithmetic.
        base = cidr.rsplit(".", 1)[0]  # e.g. "10.100.3"
        b.emit(f"configure network add {cidr} {b.ea}")
        for r in range(p["ranges_per_net"]):
            b.emit(
                f"configure network {cidr} range add {base}.{10 + r * 30} {base}.{10 + r * 30 + 20}"
            )
        # Start after the range area and take as many usable hosts as the
        # selected scale requests. The /22 layout gives production enough host
        # addresses for 500 fixed records without invalid .256-style IPs.
        fixed_hosts = list(net.hosts())[100 : 100 + p["fixed_per_net"]]
        for f, ip in enumerate(fixed_hosts):
            mac = f"aa:bb:{(i >> 8) & 0xFF:02x}:{i & 0xFF:02x}:{(f >> 8) & 0xFF:02x}:{f & 0xFF:02x}"
            b.emit(f"configure network {cidr} fixed add {ip} {mac}")

    # IPv6 networks.
    for i in range(v6):
        b.emit(f"configure network add {v6_network_cidr(i)} {b.ea}")

    # MAC filters.
    for i in range(p["option_filters"]):
        b.emit(f"configure network macfilter add smoke-macfilt-{i:02d}")


def phase3_dns_zones(b: Builder, p: dict) -> None:
    """Forward + reverse authoritative zones."""
    n = p["fwd_zones"] + p["rev_zones"]
    b.header("PHASE 3 - DNS zones (forward + reverse)", n)

    for i in range(p["fwd_zones"]):
        b.emit(f"configure zone add {fwd_zone_fqdn(i)} {b.ea}")

    for i in range(p["rev_zones"]):
        # Matches phase-2 networks so PTR records can attach later.
        b.emit(f"configure zone add {rev_zone_fqdn(i)} {b.ea}")


def phase4_dns_records(b: Builder, p: dict) -> None:
    """A/AAAA/CNAME/MX/TXT/CAA/NAPTR/TLSA records per zone, plus one PTR
    for every A and AAAA record.

    PTR coverage relies on the RFC 6303 umbrella zones emitted by phase 11
    - specifically ``10.in-addr.arpa`` (covers the whole 10.0.0.0/8, so
    our 10.200.x A records land there) and ``8.b.d.0.1.0.0.2.ip6.arpa``
    (covers 2001:db8::/32, so our 2001:db8:… AAAA records land there).
    That means phase 11 must run before phase 4 - which the default phase
    order (``0,1,2,10,3,11,4,5,6,7,8,9``) ensures. Driving phases out of
    order drops back to whatever more-specific reverse zones exist and
    logs per-PTR errors rather than silent misses.
    """
    rpz = p["records_per_zone"]

    # Proportional per-type counts - must sum to <= records_per_zone.
    def s(pct: int) -> int:
        return max(1, rpz * pct // 100)

    n_a, n_aaaa, n_cname = s(40), s(20), s(12)
    n_mx, n_txt, n_caa, n_naptr, n_tlsa = s(6), s(12), s(4), s(3), s(3)
    per_zone = n_a + n_aaaa + n_cname + n_mx + n_txt + n_caa + n_naptr + n_tlsa
    # Two extra lines per A and AAAA: the forward record then its PTR.
    total = (per_zone + n_a + n_aaaa) * p["fwd_zones"]
    b.header(
        f"PHASE 4 - DNS records ({per_zone}/zone + {n_a + n_aaaa} PTRs "
        f"across {p['fwd_zones']} zones)",
        total,
    )

    for z in range(p["fwd_zones"]):
        zone = fwd_zone_fqdn(z)

        for i in range(n_a):
            ip = f"10.200.{z % 256}.{i % 256}"
            host = f"host{i:03d}"
            b.emit(f"configure zone {zone} add a {host} {ip}")
            # PTR goes into the RFC 6303 10.in-addr.arpa umbrella zone.
            b.emit(f"configure zone 10.in-addr.arpa add ptr {ip} {host}.{zone}")
        for i in range(n_aaaa):
            ip6 = f"2001:db8:{z:x}::{i:x}"
            host = f"host{i:03d}"
            b.emit(f"configure zone {zone} add aaaa {host} {ip6}")
            # PTR goes into the RFC 6303 2001:db8::/32 umbrella zone.
            b.emit(f"configure zone 8.b.d.0.1.0.0.2.ip6.arpa add ptr {ip6} {host}.{zone}")
        for i in range(n_cname):
            b.emit(f"configure zone {zone} add cname alias{i:03d} host{i % n_a:03d}.{zone}")
        for i in range(n_mx):
            b.emit(f"configure zone {zone} add mx mail{i} mail{i}.{zone} {10 * (i + 1)}")
        for i in range(n_txt):
            b.emit(f'configure zone {zone} add txt spf{i} "v=spf1 include:_spf.google.com ~all"')
        for i in range(n_caa):
            b.emit(f"configure record caa add caa{i}.{zone} 0 issue letsencrypt.org")
        for i in range(n_naptr):
            b.emit(f"configure record naptr add naptr{i}.{zone}")
        for i in range(n_tlsa):
            b.emit(f"configure record tlsa add _443._tcp.tlsa{i}.{zone}")


def phase5_hosts(b: Builder, p: dict) -> None:
    """Host records, matching explicit PTRs, shared-record groups + shared
    records.

    NIOS host records already resolve reverse lookups internally, so a
    host's IP is "covered" without a separate PTR object. We still emit
    an explicit ``record:ptr`` per host for parity with the A/AAAA
    phase - the smoke then exercises both the implicit (host-driven)
    and explicit (record:ptr) reverse paths and downstream tooling sees
    a PTR record for every forward record.
    """
    # One PTR per host + hosts themselves.
    total = (2 * p["host_records"]) + p["shared_rec_groups"] * (1 + p["shared_records_per_grp"])
    b.header("PHASE 5 - Hosts + PTRs + shared records", total)

    # Host records across the forward zones.
    for i in range(p["host_records"]):
        z = i % max(1, p["fwd_zones"])
        zone = fwd_zone_fqdn(z)
        ip = f"10.210.{(i // 256) % 256}.{i % 256}"
        host = f"shost{i:04d}"
        b.emit(f"configure zone {zone} add host {host} {ip}")
        b.emit(f"configure zone 10.in-addr.arpa add ptr {ip} {host}.{zone}")

    # Shared-record groups + shared records.
    for g in range(p["shared_rec_groups"]):
        grp = f"smoke-srg-{g:02d}"
        b.emit(f"configure shared_record_group add {grp}")
        for i in range(p["shared_records_per_grp"]):
            b.emit(
                f"configure shared_record a add share{i:02d} 10.220.{g % 256}.{i % 256} group={grp}"
            )


def phase6_rpz(b: Builder, p: dict) -> None:
    """RPZ zones + A-type block records."""
    total = p["rpz_zones"] * (1 + p["rpz_records_per_zone"])
    b.header("PHASE 6 - RPZ zones + records", total)

    for i in range(p["rpz_zones"]):
        rpz_zone = f"smoke-rpz{i:02d}.example.com"
        b.emit(f"configure rpz zone add {rpz_zone} policy=GIVEN")
        for r in range(p["rpz_records_per_zone"]):
            target = f"bad{r:03d}.{rpz_zone}"
            b.emit(f"configure rpz record a add {target} 127.0.0.{1 + (r % 254)} zone {rpz_zone}")


def phase7_dtc(b: Builder, p: dict) -> None:
    """Full DTC coverage - every monitor type, plus pool→monitor,
    pool→server, and lbdn→pool linkages. Topologies with rules/labels
    round out the object surface.

    Monitor-type coverage cycles across the six NIOS supports
    (http, icmp, tcp, snmp, sip, pdp) so the ``show dtc monitor *``
    commands all have something to return in downstream sweeps.
    """
    n_mon = p["dtc_monitors"]
    n_srv = p["dtc_servers"]
    n_pool = p["dtc_pools"]
    n_lbdn = p["dtc_lbdns"]
    n_topo = p.get("dtc_topologies", 0)

    # Linkage fan-outs - each pool gets k servers + 1 monitor; each lbdn
    # gets k pools. Bounded so we don't emit absurdly long lines on big
    # scales.
    servers_per_pool = min(5, max(1, n_srv // max(1, n_pool)))
    pools_per_lbdn = min(3, max(1, n_pool // max(1, n_lbdn)))

    # Rough count for the header (monitors + servers + pools + lbdns
    # + pool-server and pool-monitor wires + lbdn-pool wires + topos).
    total = (
        n_mon
        + n_srv
        + n_pool
        + n_lbdn
        + n_pool * servers_per_pool
        + n_pool
        + n_lbdn * pools_per_lbdn
        + n_topo * 3
    )
    b.header("PHASE 7 - DTC (monitors, servers, pools, lbdns, topologies)", total)

    # 1) Monitors - each type has its own required fields.
    for i in range(n_mon):
        name, kind = dtc_monitor_name(i), dtc_monitor_kind(i)
        # `tcp` needs port; `snmp`/`sip`/`pdp` also port; http/icmp are fine
        # without additional fields.
        extra = ""
        if kind == "tcp":
            extra = " port=80"
        elif kind == "snmp":
            extra = " port=161"
        elif kind == "sip":
            extra = " port=5060 transport=TCP"
        elif kind == "pdp":
            extra = " port=3868"
        b.emit(f"configure dtc monitor {kind} add {name}{extra}")

    # 2) Servers (dtc:server - host is required).
    for i in range(n_srv):
        host = f"10.240.{(i // 256) % 256}.{i % 256}"
        b.emit(f"configure dtc server add {dtc_server_name(i)} host={host}")

    # 3) Pools.
    for i in range(n_pool):
        b.emit(f"configure dtc pool add {dtc_pool_name(i)} lb_preferred_method=ROUND_ROBIN")

    # 4) Pool→server linkages (round-robin assignment).
    for p_idx in range(n_pool):
        pool = dtc_pool_name(p_idx)
        for s in range(servers_per_pool):
            srv_idx = (p_idx * servers_per_pool + s) % max(1, n_srv)
            b.emit(f"configure dtc pool {pool} server add {dtc_server_name(srv_idx)}")

    # 5) Pool→monitor linkage - one monitor per pool. Picks a compatible
    # monitor by matching on kind (pool inherits the monitor's type).
    for p_idx in range(n_pool):
        pool = dtc_pool_name(p_idx)
        mon_i = p_idx % max(1, n_mon)
        mname, mkind = dtc_monitor_name(mon_i), dtc_monitor_kind(mon_i)
        b.emit(f"configure dtc pool {pool} monitor add {mkind} {mname}")

    # 6) LBDNs and their pool linkages.
    for i in range(n_lbdn):
        lbdn = dtc_lbdn_name(i)
        b.emit(f"configure dtc lbdn add {lbdn} lb_method=ROUND_ROBIN")
        for j in range(pools_per_lbdn):
            pool_idx = (i * pools_per_lbdn + j) % max(1, n_pool)
            b.emit(f"configure dtc lbdn {lbdn} pool add {dtc_pool_name(pool_idx)}")

    # 7) Topologies with one label + one rule each. NIOS requires a rule
    # chain before the topology is routable; the label is the destination.
    for i in range(n_topo):
        topo = dtc_topology_name(i)
        label = dtc_label_name(i)
        b.emit(f"configure dtc topology add {topo}")
        # Label points at an existing LBDN (wraps around if fewer LBDNs).
        target_lbdn = dtc_lbdn_name(i % max(1, n_lbdn))
        b.emit(
            f"configure dtc topology {topo} label add {label} "
            f"dest_type=LBDN destination_link={target_lbdn}"
        )
        # Catch-all rule that sends everything to the label above.
        b.emit(
            f"configure dtc topology {topo} rule add dest={label} "
            f"return_type=REGULAR sources=0.0.0.0/0"
        )


def phase8_admin(b: Builder, p: dict) -> None:
    """Admin roles, groups, users. Users reference a fresh smoke group so we
    don't pollute the built-in admin-group membership."""
    total = p["admin_users"] + p["admin_groups"] + p["admin_roles"] + 1
    b.header("PHASE 8 - Admin users, groups, roles", total)

    # Roles first (groups can reference them).
    for i in range(p["admin_roles"]):
        b.emit(f"configure admin role add smoke-role-{i:02d}")

    # Base smoke group that all smoke users get added to. We create it here
    # (separately from the counted `admin_groups` below) so phase 8 can run
    # standalone.
    b.emit(f"configure admin group add {SMOKE_ADMIN_GROUP}")

    for i in range(p["admin_groups"]):
        b.emit(f"configure admin group add smoke-group-{i:02d}")

    # Users must reference at least one existing admin group.
    for i in range(p["admin_users"]):
        b.emit(
            f"configure admin user add smoke-user-{i:02d} "
            f"password=Smoke-pw-{i:02d}! group={SMOKE_ADMIN_GROUP}"
        )


def phase9_notifications(b: Builder, p: dict) -> None:
    """Notification endpoints + rules. Rules reference endpoints by name."""
    total = p["notify_endpoints"] + p["notify_rules"]
    b.header("PHASE 9 - Notifications (endpoints + rules)", total)

    for i in range(p["notify_endpoints"]):
        b.emit(
            f"configure notification endpoint add smoke-ep-{i:02d} "
            f"uri=https://smoke-endpoint-{i:02d}.example.com/webhook"
        )

    for i in range(p["notify_rules"]):
        ep = f"smoke-ep-{i % max(1, p['notify_endpoints']):02d}"
        b.emit(f"configure notification rule add smoke-rule-{i:02d} endpoint={ep}")


def phase10_dhcp_extras(b: Builder, p: dict) -> None:
    """DHCP-adjacent objects not covered by phase 2: option spaces, DHCP
    filters across all five types, network/range templates."""
    total = (
        p["option_spaces"]
        + p["filters_option"]
        + p["filters_nac"]
        + p["filters_ipv6option"]
        + p["filters_relayagent"]
        + p["net_templates"]
        + p["range_templates"]
    )
    b.header("PHASE 10 - DHCP extras (option spaces, filters, templates)", total)

    for i in range(p["option_spaces"]):
        b.emit(f"configure option_space add smoke-optspace-{i:02d}")

    # DHCP option filters - 4 of the 5 types work with just a name. The 5th
    # (fingerprint) requires referencing an existing Fingerprint definition,
    # which we don't have on a fresh grid; skip it rather than synthesize a
    # fake fingerprint record.
    #
    # NIOS rejects a filteroption / ipv6filteroption that has no option_list
    # *and* no expression with "Rule list must contain at least one rule
    # value or a list." Earlier releases accepted empty filters, so this was
    # latent; newer builds enforce it. Downstream tools (UDDI / CSP
    # global-csv import) additionally require an explicit *match rule* -
    # they won't infer one from `apply_as_class=True` + option_list. So we
    # emit both:
    #   - rule=<opt_name>:<value>:<num>   → option_list (what to serve)
    #   - match=<opt_name>:<value>        → expression (who to match)
    # The expression ends up in the CSV export's `expression` column,
    # which UDDI/CSP reads directly.
    for i in range(p["filters_option"]):
        # vendor-class-identifier (option 60) is a standard DHCPv4 option
        # that's always defined, so this works on any grid.
        b.emit(
            f"configure filter option add smoke-filt-opt-{i:02d} "
            f'match=vendor-class-identifier:"smoke-class-{i:02d}" '
            f'rule=vendor-class-identifier:"smoke-class-{i:02d}":60'
        )
    for i in range(p["filters_nac"]):
        b.emit(f"configure filter nac add smoke-filt-nac-{i:02d}")
    for i in range(p["filters_ipv6option"]):
        # dhcp6.vendor-class (DHCPv6 option 16) is the canonical built-in
        # v6 option name in NIOS. Note the "dhcp6." prefix is required.
        b.emit(
            f"configure filter ipv6option add smoke-filt-v6o-{i:02d} "
            f'match=dhcp6.vendor-class:"smoke-v6class-{i:02d}" '
            f'rule=dhcp6.vendor-class:"smoke-v6class-{i:02d}":16'
        )
    for i in range(p["filters_relayagent"]):
        # NIOS rejects both fields being ANY simultaneously. Give each filter
        # a specific remote_id value; keep circuit_id as ANY so it matches
        # any circuit.
        b.emit(
            f"configure filter relayagent add smoke-filt-ra-{i:02d} "
            f"is_circuit_id=ANY is_remote_id=MATCHES_VALUE "
            f"remote_id_name=smoke-remote-{i:02d} "
            f"is_remote_id_substring=false"
        )

    # Network templates - cidr is required.
    for i in range(p["net_templates"]):
        b.emit(f"configure template network add smoke-nettmpl-{i:02d} cidr 24")

    # Range templates - number_of_addresses + offset required.
    for i in range(p["range_templates"]):
        b.emit(
            f"configure template range add smoke-rangetmpl-{i:02d} number_of_addresses=10 offset=10"
        )


def phase11_rfc_local_zones(b: Builder, p: dict) -> None:
    """RFC 6303 + RFC 6598 locally-served reverse zones.

    Every recursive resolver SHOULD answer these zones locally per RFC
    6303 ("Locally Served DNS Zones") to avoid leaking reverse lookups
    for private, link-local, loopback, documentation, and test address
    space out to the internet roots. RFC 6598 extends the v4 list with
    the 100.64.0.0/10 CGN block (64 per-byte zones).

    Total: ~80 zones. They're emitted independently of the scale preset
    because the RFC list is fixed; scale only affects how much *else*
    the smoke puts on the grid.

    Zone format (IPV4 vs IPV6) is inferred by the CLI from the
    .in-addr.arpa / .ip6.arpa suffix - no explicit keyword needed.
    """
    # The `p` param is unused but kept to match the phase-fn signature.
    _ = p
    zones = RFC_LOCAL_ZONES
    b.header(
        "PHASE 11 - RFC 6303 + RFC 6598 locally-served reverse zones",
        len(zones),
    )
    for fqdn in zones:
        b.emit(f"configure zone add {fqdn} {b.ea}")


def phase12_production_extras(b: Builder, p: dict) -> None:
    """Production-scale coverage of object types the earlier phases miss.

    Every count defaults to 0 so tiny/small/full don't touch anything here;
    only the ``production`` scale turns these on. See SCALE["production"]
    in _shared.py for the specific counts.

    Covered:

    - network containers (v4 + v6)
    - network views (in addition to DNS views from phase 1)
    - VLAN views / VLAN ranges / VLANs
    - roaming hosts, bulk hosts
    - custom option definitions (optiondef, ipv6optiondef)
    - fingerprint definitions
    - record-name and hostname policies
    - BFD templates, NAT groups, RIR organizations
    - upgrade groups
    - extra DNS DNAME records per zone

    Intentionally skipped (they need external state or hardware we can't
    synthesize in smoke):

    - HSM, CA certificates, kerberos keys
    - MS server / MS superscope (needs MS-AD integration)
    - Discovery / vdiscovery / external integrations
      (taxii, syslog, pxgrid, dxl)
    """
    counts = [
        p.get("network_views", 0),
        p.get("vlan_views", 0),
        p.get("roaming_hosts", 0),
        p.get("bulk_hosts", 0),
        p.get("optiondefs_v4", 0),
        p.get("optiondefs_v6", 0),
        p.get("fingerprint_defs", 0),
        p.get("record_name_policies", 0),
        p.get("hostname_policies", 0),
        p.get("bfd_templates", 0),
        p.get("nat_groups", 0),
        p.get("rir_orgs", 0),
        p.get("upgrade_groups", 0),
    ]
    if sum(counts) == 0 and p.get("dname_records_per_zone", 0) == 0:
        return

    total = (
        sum(counts)
        + p.get("vlan_views", 0) * p.get("vlans_per_view", 0)
        + p.get("dname_records_per_zone", 0) * p.get("fwd_zones", 0)
    )
    b.header("PHASE 12 - Production extras (remaining object types)", total)

    # Extra network views (besides the DNS `view` objects phase 1 creates).
    for i in range(p.get("network_views", 0)):
        b.emit(f"configure network_view add {network_view_name(i)}")

    # VLAN views, ranges, and vlans. A VLAN range needs a view and a span;
    # the VLANs live inside the range.
    for i in range(p.get("vlan_views", 0)):
        vv = vlan_view_name(i)
        b.emit(f"configure vlan_view add {vv} start_vlan_id=1 end_vlan_id=4094")
        # Emit a single covering range, then populate VLANs inside it.
        rng = f"{vv}-range"
        b.emit(f"configure vlan_range add {rng} vlan_view={vv} start_vlan_id=1 end_vlan_id=4094")
        for v in range(p.get("vlans_per_view", 0)):
            vid = 100 + v  # avoid system-reserved 1-99
            b.emit(f"configure vlan add {vid} name=smoke-vlan-{i:02d}-{v:04d} parent={rng}")

    # Roaming hosts - MAC-keyed DHCP hosts not tied to a subnet.
    for i in range(p.get("roaming_hosts", 0)):
        b.emit(f"configure roaming_host add {roaming_host_name(i)}")

    # Bulk hosts - template-expanded A/PTR groups. Uses a /29 so NIOS
    # generates 8 A records per bulk-host definition.
    for i in range(p.get("bulk_hosts", 0)):
        octet3 = 230 + (i // 256)
        octet2 = i % 256
        start = f"10.{octet3}.{octet2}.0"
        end = f"10.{octet3}.{octet2}.7"
        b.emit(f"configure bulkhost add {bulkhost_name(i)} start_addr={start} end_addr={end}")

    # Custom DHCP option definitions (IPv4 and IPv6). Option spaces created
    # in phase 10 host them.
    for i in range(p.get("optiondefs_v4", 0)):
        space = f"smoke-optspace-{i % max(1, p.get('option_spaces', 1)):02d}"
        code = 224 + i  # 224-254 is the vendor-custom range
        b.emit(
            f"configure optiondef add smoke-opt-v4-{i:02d} code {code} type string space={space}"
        )
    for i in range(p.get("optiondefs_v6", 0)):
        space = f"smoke-optspace-{i % max(1, p.get('option_spaces', 1)):02d}"
        code = 256 + i
        b.emit(
            f"configure ipv6optiondef add smoke-opt-v6-{i:02d} "
            f"code {code} type string space={space}"
        )

    # Device/client fingerprint definitions (used by filter fingerprint).
    for i in range(p.get("fingerprint_defs", 0)):
        b.emit(f"configure fingerprint add smoke-fp-{i:02d} vendor_id=smoke-vendor-{i:02d}")

    # Record-name and hostname policies.
    for i in range(p.get("record_name_policies", 0)):
        b.emit(f'configure record_name_policy add smoke-rnp-{i:02d} regex="^[a-z0-9-]+$"')
    for i in range(p.get("hostname_policies", 0)):
        b.emit(
            f"configure hostname_policy add smoke-hnp-{i:02d} "
            f"valid_characters=abcdefghijklmnopqrstuvwxyz0123456789- "
            f"replacement_character=-"
        )

    # BFD templates.
    for i in range(p.get("bfd_templates", 0)):
        b.emit(f"configure bfd_template add smoke-bfd-{i:02d}")

    # NAT groups.
    for i in range(p.get("nat_groups", 0)):
        b.emit(f"configure nat_group add smoke-nat-{i:02d}")

    # RIR organizations.
    for i in range(p.get("rir_orgs", 0)):
        b.emit(f"configure rir_organization add smoke-rir-{i:02d} rir=ARIN")

    # Upgrade groups.
    for i in range(p.get("upgrade_groups", 0)):
        b.emit(f"configure upgrade_group add smoke-ug-{i:02d}")

    # Extra DNS record type not in phase 4's mix. Keep this to command shapes
    # ibcli supports today; unsupported DNSSEC/SRV/SSHFP handlers can be added
    # later alongside their own command implementations.
    extras = p.get("dname_records_per_zone", 0)
    fwd_zones = p.get("fwd_zones", 0)
    if extras and fwd_zones:
        for z in range(fwd_zones):
            zone = fwd_zone_fqdn(z)
            for i in range(extras):
                b.emit(f"configure record dname add dname{i}.{zone} dname-target{i}.example.net")


PHASES = {
    0: phase0_members,
    1: phase1_infrastructure,
    2: phase2_dhcp,
    3: phase3_dns_zones,
    4: phase4_dns_records,
    5: phase5_hosts,
    6: phase6_rpz,
    7: phase7_dtc,
    8: phase8_admin,
    9: phase9_notifications,
    10: phase10_dhcp_extras,
    11: phase11_rfc_local_zones,
    12: phase12_production_extras,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--tag",
        default="yes",
        help="Value stored in the Smoke EA on objects that support EA tagging at add time.",
    )
    ap.add_argument("--scale", choices=list(SCALE), default="full")
    ap.add_argument(
        "--members",
        type=int,
        default=None,
        help="Override the scale's member count (e.g. 200). "
        "Everything that references members - NS groups, "
        "failover peers - follows the new count.",
    )
    ap.add_argument(
        "--grid",
        default=None,
        help="Grid name for `configure grid <name> member add`. "
        "Defaults to IBCLI_SMOKE_GRID or 'Migration'. Must "
        "match `show grid` on the target or member adds fail.",
    )
    ap.add_argument(
        "--phases",
        default="0,1,2,10,3,11,4,5,6,7,8,9,12",
        help="Comma-separated phase numbers to emit, in "
        "order. Default creates members first (0), then "
        "infrastructure (1), then DHCP (2), then DHCP "
        "extras/templates (10), then zones (3) including "
        "the RFC 6303/6598 locally-served reverse zones "
        "(11), then records/hosts/RPZ/DTC/admin/"
        "notifications, and finally production-extras "
        "(12 - no-op unless --scale=production).",
    )
    args = ap.parse_args()

    phases = [int(x) for x in args.phases.split(",") if x.strip()]
    # Copy so an override never mutates the shared SCALE table.
    params = dict(SCALE[args.scale])
    if args.members is not None:
        if args.members < 0:
            ap.error("--members must be >= 0")
        params["members"] = args.members
    if args.grid:
        # _shared.GRID_NAME is read at import time by build/teardown/verify;
        # rebind it here so every phase emits the right grid name.
        import _shared

        _shared.GRID_NAME = args.grid
        globals()["GRID_NAME"] = args.grid
    b = Builder(args.tag)

    b.emit("# ibcli smoke-test build script")
    b.emit(f"# scale={args.scale}  tag={args.tag}  phases={phases}")
    b.emit(f"# grid={globals()['GRID_NAME']}  members={params['members']}")
    b.emit("# Run with: ibcli -i -s <host> -u <user> -p <pw> -k smoke-build.ibcli")
    b.emit("# All smoke-created objects carry the 'smoke-' name prefix; those")
    b.emit("# whose grammar accepts it at add time also carry the Smoke EA.")

    for n in phases:
        if n not in PHASES:
            print(f"# skipping unknown phase {n}", file=sys.stderr)
            continue
        PHASES[n](b, params)


if __name__ == "__main__":
    main()
