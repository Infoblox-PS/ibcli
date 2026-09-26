# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Shared constants and name-builders for the smoke harness.

Imported by build.py, teardown.py, and verify.py so they agree on scale
presets and object-name conventions. Drift here would silently break
teardown (names created by build wouldn't match names deleted by teardown).
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Grid / member topology
# ---------------------------------------------------------------------------

# Grid name differs per lab, and `configure grid <name> member add` fails if it
# is wrong. Override with IBCLI_SMOKE_GRID (or build.py --grid) rather than
# editing this file.
GRID_NAME = os.environ.get("IBCLI_SMOKE_GRID", "Migration")
SMOKE_ADMIN_GROUP = "smoke-group-base"

# Pre-provisioned members live on their own subnet so they can never collide
# with the real grid master's address. They are database records, not running
# appliances, so the addresses need not be reachable.
MEMBER_NET_PREFIX = os.environ.get("IBCLI_SMOKE_MEMBER_NET", "10.63.50")


# ---------------------------------------------------------------------------
# Name builders - the ONE place that maps phase index → object name.
# ---------------------------------------------------------------------------


def member_fqdn(i: int) -> str:
    return f"smoke-mbr{i:02d}.example.com"


def smoke_members(n: int) -> list[str]:
    return [member_fqdn(i) for i in range(n)]


def member_ipv4(i: int) -> str:
    """Return the /24 CIDR for member *i*.

    Walks host addresses .2-.255 and rolls into the next third octet, so the
    scheme keeps working past a single /24 - the old ``.{200 + i}`` formula
    produced invalid addresses (.256+) from the 56th member onward, which only
    stayed hidden because no scale asked for more than six.
    """
    per_subnet = 254 - 1  # .2 through .254; .1 is the gateway, .255 broadcast
    third = int(MEMBER_NET_PREFIX.split(".")[2]) + i // per_subnet
    host = 2 + (i % per_subnet)
    a, b, _ = MEMBER_NET_PREFIX.split(".")
    return f"{a}.{b}.{third}.{host}/24"


def _member_subnet(i: int) -> str:
    """Return the first three octets of member *i*'s subnet."""
    return member_ipv4(i).split("/")[0].rsplit(".", 1)[0]


def member_gateway(i: int) -> str:
    """Gateway for member *i* - always .1 of that member's own subnet."""
    return f"{_member_subnet(i)}.1"


def member_ipv6(i: int) -> str:
    third = _member_subnet(i).rsplit(".", 1)[1]
    return f"2001:db8:63:{third}::{2 + i:x}/64"


# Member feature variants. Cycling by index gives broad coverage of the
# interface shapes NIOS supports without adding a scale key per feature:
# every 5th member is plain, and the others exercise VLAN tagging, a MGMT
# port, an HA pair, and port redundancy respectively.
MEMBER_VARIANTS = ("plain", "vlan", "mgmt", "ha", "portred")

# Dedicated /24 per HA member. NIOS wants each node's LAN1 and HA addresses
# in the same subnet as the HA VIP, which is five addresses per member - far
# more than the shared member subnet can spare at 200 members.
HA_NET_PREFIX = os.environ.get("IBCLI_SMOKE_HA_NET", "10.68")
MGMT_NET_PREFIX = os.environ.get("IBCLI_SMOKE_MGMT_NET", "10.65")
LAN2_NET_PREFIX = os.environ.get("IBCLI_SMOKE_LAN2_NET", "10.66")


def member_variant(i: int) -> str:
    """Which interface shape member *i* is built with."""
    return MEMBER_VARIANTS[i % len(MEMBER_VARIANTS)]


def member_vlan_id(i: int) -> int:
    """802.1Q tag for member *i*'s LAN1. Kept inside the valid 1-4094 range."""
    return 100 + (i % 3900)


def member_mgmt_ipv4(i: int) -> str:
    """MGMT address for member *i*.

    Strides by two so an HA member's two node addresses (see
    `member_ha_addrs`) fit beside it in the same /24 without colliding with
    the next member's allocation.
    """
    return f"{MGMT_NET_PREFIX}.{i // 126}.{2 + 2 * (i % 126)}/24"


def member_mgmt_gateway(i: int) -> str:
    """MGMT gateway - .1 of that member's own MGMT subnet."""
    return f"{MGMT_NET_PREFIX}.{i // 126}.1"


def member_lan2_ipv4(i: int) -> str:
    return f"{LAN2_NET_PREFIX}.{i // 254}.{2 + (i % 254)}/24"


def member_lan2_gateway(i: int) -> str:
    return f"{LAN2_NET_PREFIX}.{i // 254}.1"


def member_ha_addrs(i: int) -> dict[str, str]:
    """Addresses for HA member *i*: VIP, both nodes' LAN1 and HA ports.

    All five live in one dedicated /24 because NIOS requires the nodes' LAN1
    addresses to share the VIP's subnet.
    """
    third = i % 256
    net = f"{HA_NET_PREFIX}.{third}"
    return {
        "vip": f"{net}.5/24",
        "gateway": f"{net}.1",
        "node1_lan1": f"{net}.6",
        "node1_ha": f"{net}.8",
        "node2_lan1": f"{net}.7",
        "node2_ha": f"{net}.9",
        # Both nodes' MGMT addresses must sit in the same /24 as the MGMT
        # gateway - NIOS rejects "The gateway address <gw> must be in the
        # same subnet as the IP address <ip> for MGMT". Allocate two
        # consecutive hosts per member so the pair always shares a subnet.
        "node1_mgmt": f"{MGMT_NET_PREFIX}.{i // 126}.{2 + 2 * (i % 126)}",
        "node2_mgmt": f"{MGMT_NET_PREFIX}.{i // 126}.{3 + 2 * (i % 126)}",
    }


def member_router_id(i: int) -> int:
    """VRRP virtual router id for HA member *i*. NIOS requires 1-255."""
    return 1 + (i % 255)


def member_ipv6_gateway(i: int) -> str:
    third = _member_subnet(i).rsplit(".", 1)[1]
    return f"2001:db8:63:{third}::1"


def fwd_zone_fqdn(i: int) -> str:
    return f"smoke-zone{i:03d}.example.com"


def rev_zone_fqdn(i: int) -> str:
    """Per-index reverse zone used for specific reverse-zone coverage."""
    return f"{i}.100.10.in-addr.arpa"


def v4_network_cidr(i: int) -> str:
    # Production needs 500 usable fixed-address slots per network. Use /22s
    # and stride by four third-octets so networks never overlap.
    base_octet = i * 4
    return f"10.{100 + (base_octet // 256)}.{base_octet % 256}.0/22"


def v6_network_cidr(i: int) -> str:
    return f"2001:db8:{i:x}::/64"


def v4_container_cidr(i: int) -> str:
    """/16 containers holding groups of v4 networks."""
    return f"10.{100 + i}.0.0/16"


def v6_container_cidr(i: int) -> str:
    """/48 containers holding groups of v6 networks."""
    return f"2001:db8:{0x1000 + i:x}::/48"


def failover_name(i: int) -> str:
    return f"smoke-fo-{i:02d}"


def network_view_name(i: int) -> str:
    return f"smoke-nv-{i:03d}"


def vlan_view_name(i: int) -> str:
    return f"smoke-vlanview-{i:02d}"


def roaming_host_name(i: int) -> str:
    return f"smoke-roam-{i:04d}"


def bulkhost_name(i: int) -> str:
    return f"smoke-bulk{i:03d}"


def dtc_monitor_kind(i: int) -> str:
    return ("http", "icmp", "tcp", "snmp", "sip", "pdp")[i % 6]


def dtc_monitor_name(i: int) -> str:
    kind = dtc_monitor_kind(i)
    return f"smoke-mon{i:03d}-{kind}"


def dtc_server_name(i: int) -> str:
    return f"smoke-srv{i:04d}"


def dtc_pool_name(i: int) -> str:
    return f"smoke-pool{i:03d}"


def dtc_lbdn_name(i: int) -> str:
    return f"smoke-lbdn{i:03d}"


def dtc_topology_name(i: int) -> str:
    return f"smoke-topo{i:02d}"


def dtc_label_name(i: int) -> str:
    return f"smoke-lbl-{i:02d}"


# ---------------------------------------------------------------------------
# Scale presets - keys consumed by every phase function in build/teardown.
# ---------------------------------------------------------------------------

SCALE: dict[str, dict[str, int]] = {
    "tiny": {
        "members": 2,
        "eas": 3,
        "option_spaces": 1,
        "filters_option": 1,
        "filters_nac": 1,
        "filters_ipv6option": 1,
        "filters_relayagent": 1,
        "net_templates": 1,
        "range_templates": 1,
        "views": 2,
        "nsgroups": 2,
        "acls": 3,
        "networks_v4": 2,
        "networks_v6": 1,
        "ranges_per_net": 1,
        "fixed_per_net": 3,
        "option_filters": 1,
        "failovers": 1,
        "fwd_zones": 3,
        "rev_zones": 2,
        "records_per_zone": 5,
        "host_records": 5,
        "shared_rec_groups": 1,
        "shared_records_per_grp": 2,
        "rpz_zones": 2,
        "rpz_records_per_zone": 3,
        "dtc_servers": 3,
        "dtc_pools": 2,
        "dtc_lbdns": 1,
        "dtc_monitors": 6,
        "dtc_topologies": 1,
        "admin_users": 3,
        "admin_groups": 2,
        "admin_roles": 2,
        "notify_endpoints": 1,
        "notify_rules": 0,  # rules need expression_list
    },
    "small": {
        "members": 4,
        "eas": 5,
        "option_spaces": 2,
        "filters_option": 3,
        "filters_nac": 2,
        "filters_ipv6option": 2,
        "filters_relayagent": 2,
        "net_templates": 3,
        "range_templates": 3,
        "views": 3,
        "nsgroups": 2,
        "acls": 5,
        "networks_v4": 10,
        "networks_v6": 3,
        "ranges_per_net": 2,
        "fixed_per_net": 10,
        "option_filters": 3,
        "failovers": 2,
        "fwd_zones": 10,
        "rev_zones": 5,
        "records_per_zone": 20,
        "host_records": 30,
        "shared_rec_groups": 3,
        "shared_records_per_grp": 5,
        "rpz_zones": 5,
        "rpz_records_per_zone": 10,
        "dtc_servers": 10,
        "dtc_pools": 5,
        "dtc_lbdns": 3,
        "dtc_monitors": 6,
        "dtc_topologies": 2,
        "admin_users": 5,
        "admin_groups": 3,
        "admin_roles": 3,
        "notify_endpoints": 3,
        "notify_rules": 0,  # rules need expression_list
    },
    "full": {
        "members": 6,
        "eas": 20,
        "option_spaces": 5,
        "filters_option": 10,
        "filters_nac": 5,
        "filters_ipv6option": 5,
        "filters_relayagent": 5,
        "net_templates": 10,
        "range_templates": 10,
        "views": 5,
        "nsgroups": 3,
        "acls": 10,
        "networks_v4": 40,
        "networks_v6": 10,
        "ranges_per_net": 3,
        "fixed_per_net": 20,
        "option_filters": 5,
        "failovers": 3,
        "fwd_zones": 50,
        "rev_zones": 30,
        "records_per_zone": 80,  # ~50*80 = 4,000 forward records
        "host_records": 800,
        "shared_rec_groups": 5,
        "shared_records_per_grp": 10,
        "rpz_zones": 20,
        "rpz_records_per_zone": 25,
        "dtc_servers": 50,
        "dtc_pools": 20,
        "dtc_lbdns": 10,
        "dtc_monitors": 30,
        "dtc_topologies": 5,
        "admin_users": 20,
        "admin_groups": 10,
        "admin_roles": 10,
        "notify_endpoints": 10,
        "notify_rules": 0,  # rules need expression_list
        # Phase 12 (production extras) - zeroed at the smaller scales so the
        # build stays short unless you opt in.
        "network_containers_v4": 0,
        "network_containers_v6": 0,
        "network_views": 0,
        "vlan_views": 0,
        "vlans_per_view": 0,
        "roaming_hosts": 0,
        "bulk_hosts": 0,
        "optiondefs_v4": 0,
        "optiondefs_v6": 0,
        "fingerprint_defs": 0,
        "record_name_policies": 0,
        "hostname_policies": 0,
        "bfd_templates": 0,
        "nat_groups": 0,
        "rir_orgs": 0,
        "upgrade_groups": 0,
        # Extra DNS record types not in Phase 4's default mix.
        "dname_records_per_zone": 0,
    },
    # ---------------------------------------------------------------------
    # production - 250K+ DNS records, 250K+ DHCP fixed addresses, every
    # object type ibcli can create. Multi-hour build against a live grid.
    # TAKE A BACKUP FIRST - see scripts/smoke/backup.py.
    # ---------------------------------------------------------------------
    "production": {
        "members": 6,
        "eas": 30,
        "option_spaces": 10,
        "filters_option": 20,
        "filters_nac": 10,
        "filters_ipv6option": 10,
        "filters_relayagent": 10,
        "net_templates": 20,
        "range_templates": 20,
        "views": 10,
        "nsgroups": 10,
        "acls": 30,
        # DHCP core - 500 v4 networks × 500 fixed ≈ 250K fixed addresses.
        "networks_v4": 500,
        "networks_v6": 50,
        "ranges_per_net": 3,
        "fixed_per_net": 500,
        "option_filters": 20,
        "failovers": 3,
        # DNS core - 500 forward zones × 500 records/zone ≈ 250K forward
        # records, plus ~175K PTRs (one per A/AAAA). Reverse zones follow
        # the v4 network layout so PTRs have somewhere to land.
        "fwd_zones": 500,
        "rev_zones": 250,
        "records_per_zone": 500,
        "host_records": 5000,
        "shared_rec_groups": 20,
        "shared_records_per_grp": 50,
        "rpz_zones": 50,
        "rpz_records_per_zone": 100,
        "dtc_servers": 2000,
        "dtc_pools": 200,
        "dtc_lbdns": 100,
        "dtc_monitors": 120,
        "dtc_topologies": 50,
        "admin_users": 50,
        "admin_groups": 20,
        "admin_roles": 20,
        "notify_endpoints": 20,
        "notify_rules": 0,
        # Phase 12 - production-only extras.
        "network_containers_v4": 20,
        "network_containers_v6": 10,
        "network_views": 5,
        "vlan_views": 5,
        "vlans_per_view": 50,
        "roaming_hosts": 1000,
        "bulk_hosts": 100,
        "optiondefs_v4": 20,
        "optiondefs_v6": 10,
        "fingerprint_defs": 20,
        "record_name_policies": 5,
        "hostname_policies": 5,
        "bfd_templates": 5,
        "nat_groups": 5,
        "rir_orgs": 3,
        "upgrade_groups": 3,
        "dname_records_per_zone": 10,
    },
}


# ---------------------------------------------------------------------------
# RFC 6303 + RFC 6598 locally-served reverse zones
#
# RFC 6303 ("Locally Served DNS Zones") lists the reverse zones that every
# recursive resolver SHOULD answer locally so private/experimental/link-
# local addresses don't leak to the internet root. RFC 6598 ("IANA-
# Reserved IPv4 Prefix for Shared Address Space") adds the 100.64.0.0/10
# CGN block - which means per-byte reverse zones 64.100.in-addr.arpa
# through 127.100.in-addr.arpa (64 zones).
#
# These lists are flat on purpose: the smoke build emits them verbatim as
# `configure zone add <fqdn>` and lets the CLI auto-set zone_format from
# the .in-addr.arpa / .ip6.arpa suffix.
# ---------------------------------------------------------------------------

RFC6303_V4_ZONES: list[str] = [
    # RFC 1918 private address space
    "10.in-addr.arpa",
    *[f"{i}.172.in-addr.arpa" for i in range(16, 32)],  # 172.16.0.0/12
    "168.192.in-addr.arpa",  # 192.168.0.0/16
    # RFC 3927 link-local 169.254.0.0/16
    "254.169.in-addr.arpa",
    # RFC 5737 documentation (TEST-NET-1/2/3)
    "2.0.192.in-addr.arpa",
    "100.51.198.in-addr.arpa",
    "113.0.203.in-addr.arpa",
    # This-network / loopback (RFC 1122)
    "0.in-addr.arpa",
    "127.in-addr.arpa",
    # NOTE: RFC 6303 also lists ``255.255.255.255.in-addr.arpa`` (limited
    # broadcast per RFC 922) but NIOS refuses to create it - the 4-octet
    # arpa name parses as a /32 network internally and NIOS rejects with
    # ``Invalid IPv4 netmask 32.``. Callers running a BIND-based resolver
    # should configure that zone outside NIOS.
]

RFC6303_V6_ZONES: list[str] = [
    # ULA - RFC 4193 fc00::/7, delegated as fd00::/8 in practice (d.f.ip6.arpa)
    "d.f.ip6.arpa",
    # IPv6 link-local fe80::/10 - four nibbles (8/9/a/b).e.f.ip6.arpa
    "8.e.f.ip6.arpa",
    "9.e.f.ip6.arpa",
    "a.e.f.ip6.arpa",
    "b.e.f.ip6.arpa",
    # Documentation address space 2001:db8::/32 (RFC 3849)
    "8.b.d.0.1.0.0.2.ip6.arpa",
]

# RFC 6598 Shared Address Space 100.64.0.0/10 → 64 per-byte reverse zones.
RFC6598_V4_ZONES: list[str] = [f"{i}.100.in-addr.arpa" for i in range(64, 128)]

RFC_LOCAL_ZONES: list[str] = RFC6303_V4_ZONES + RFC6303_V6_ZONES + RFC6598_V4_ZONES
