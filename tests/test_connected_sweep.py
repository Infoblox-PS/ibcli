# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Parametrized sweep running commands against a *connected* NiosClient with a
permissive mock transport. The handler returns empty lists for all GETs and 201
for POSTs. This exercises handler bodies past the "Not connected" and "Error:
required" guards covered by `test_not_connected_sweep.py`, hitting many list+
empty, "No X found", and happy-path list iterations at once.
"""

from __future__ import annotations

import httpx
import pytest

import ibcli.commands  # noqa: F401 - registers all command trees
from ibcli.context import Context
from ibcli.dispatcher import process_line
from tests.conftest import make_client


def _permissive_handler(request: httpx.Request) -> httpx.Response | None:
    path = request.url.path
    if b"_schema=1" in request.url.query or path.endswith("/grid/session"):
        return None  # delegate to default session handler

    method = request.method
    if method == "GET":
        return httpx.Response(200, json=[])
    if method == "POST":
        # Return a plausible _ref shaped for whichever object type was posted.
        obj = path.rstrip("/").rsplit("/", 1)[-1]
        return httpx.Response(201, json=f"{obj}/abc:x/default")
    if method in ("PUT", "DELETE"):
        return httpx.Response(200, json=path)
    return httpx.Response(200, json={})


_COMMANDS = [
    # Show commands - iterate an empty list → no output or header-only.
    "show zone",
    "show record host",
    "show network",
    "show network ipv6",
    "show network container",
    "show range",
    "show fixed",
    "show lease",
    "show dtc",
    "show dtc server",
    "show dtc pool",
    "show dtc lbdn",
    "show dtc monitor http",
    "show dtc topology",
    "show view",
    "show nsgroup",
    "show rpz zone",
    "show rpz record",
    "show member",
    "show auth ldap",
    "show auth ad",
    "show auth radius",
    "show auth saml",
    "show auth tacacs",
    "show auth certificate",
    "show admin user",
    "show admin role",
    "show admin group",
    "show notify endpoint",
    "show notify rule",
    "show threat protection",
    "show threat analytics",
    "show discovery",
    "show upgrade status",
    "show upgrade group",
    "show certificate",
    "show ea definition",
    "show template network",
    "show template range",
    "show record caa",
    "show record dname",
    "show record alias",
    "show record ns",
    "show record naptr",
    "show record tlsa",
    "show record https",
    "show record svcb",
    "show shared_record a",
    "show shared_record aaaa",
    "show shared_record cname",
    "show shared_record mx",
    "show shared_record txt",
    "show shared_record srv",
    "show option",
    "show rangetemplate",
    "show networktemplate",
    "show grid dns",
    "show grid dhcp",
    "show member dns",
    "show member dhcp",
    "show views",
    # Delete commands - list() returns empty → prints "No X found" and returns.
    "configure zone probe.example.com delete",
    "configure zone probe.example.com delete host web01",
    "configure zone probe.example.com delete a web",
    "configure network 10.0.0.0/24 delete",
    "configure network 10.0.0.0/24 range delete 10.0.0.10 10.0.0.20",
    "configure network 10.0.0.0/24 fixed delete 10.0.0.5",
    "configure record caa delete svc.example.com",
    "configure record dname delete sub.example.com",
    "configure record alias delete a.example.com",
    "configure record ns delete example.com",
    "configure record naptr delete svc.example.com",
    "configure record tlsa delete svc.example.com",
    "configure record https delete svc.example.com",
    "configure record svcb delete svc.example.com",
    "configure shared_record a delete www group=srg-a",
    "configure shared_record aaaa delete www group=srg-a",
    "configure shared_record cname delete www group=srg-a",
    "configure shared_record mx delete mail group=srg-a",
    "configure shared_record txt delete spf group=srg-a",
    "configure shared_record srv delete svc group=srg-a",
    "configure view External delete",
    "configure nsgroup ns1 delete",
    "configure shared_record_group srg-a delete",
    "configure dtc server web1 delete",
    "configure dtc pool p1 delete",
    "configure dtc lbdn lb1 delete",
    "configure dtc monitor http mon1 delete",
    "configure dtc topology t1 delete",
    "configure rpz zone rpz.example.com delete",
    "configure auth ldap lab-ldap delete",
    "configure auth ad lab-ad delete",
    "configure auth radius lab-radius delete",
    "configure auth saml lab-saml delete",
    "configure auth tacacs lab-tacacs delete",
    "configure auth certificate lab-cert delete",
    "configure admin user alice delete",
    "configure admin group lab-netops delete",
    "configure admin role lab-operator delete",
    "configure acl acl1 delete",
    "configure ea definition MyEA delete",
    "configure notify endpoint ep1 delete",
    "configure notify rule r1 delete",
    "configure discovery disc1 delete",
    "configure upgrade group grp1 delete",
    "configure template network tmpl1 delete",
    "configure network failover fo1 delete",
    "configure network macfilter delete macfilt1",
    # Add commands - happy path plus optional kv (view/comment/extattrs).
    "configure zone add probe.example.com",
    "configure zone add probe.example.com view=External",
    "configure zone add probe.example.com comment=staging",
    'configure zone add probe.example.com comment="staging zone"',
    "configure zone add probe.example.com set EA1 v1",
    "configure zone add probe.example.com view=External comment=staging set EA1 v1",
    "configure network add 10.0.0.0/24",
    "configure network add 10.0.0.0/24 view=External comment=core",
    "configure network add 10.0.0.0/24 member 10.0.0.2 member 10.0.0.3",
    "configure network add 10.0.0.0/24 set EA1 v1",
    "configure network add 2001:db8::/64 comment=ipv6",
    "configure record caa add svc.example.com 0 issue letsencrypt.org",
    "configure record caa add svc.example.com 0 issue letsencrypt.org view=External comment=x",
    "configure record dname add sub.example.com target.example.com view=External",
    "configure record alias add a.example.com target.example.com comment=c",
    "configure record ns add example.com ns1.example.com view=External",
    "configure record https add svc.example.com 1 target.example.com",
    "configure record svcb add svc.example.com 1 target.example.com",
    "configure view add External",
    "configure view add External comment=x",
    "configure nsgroup add ns1 primary=gm.example.com",
    "configure nsgroup add ns1 primary=gm.example.com comment=c",
    "configure shared_record_group add srg-a",
    "configure shared_record_group add srg-a comment=x",
    "configure shared_record a add www 10.0.0.1 group=srg-a",
    "configure shared_record aaaa add www 2001:db8::1 group=srg-a",
    "configure shared_record cname add www target.example.com group=srg-a",
    "configure shared_record mx add mail mail.example.com 10 group=srg-a",
    "configure shared_record txt add spf v=spf1 group=srg-a",
    "configure acl add acl1 access_list=10.0.0.0/8",
    "configure acl add acl1 access_list=10.0.0.0/8 comment=x",
    "configure rpz zone add rpz.example.com policy=GIVEN",
    "configure rpz zone add rpz.example.com policy=BLOCK",
    "configure rpz record a add bad.example.com.rpz.example.com 127.0.0.1 zone rpz.example.com",
    "configure dtc server add web1 host=10.0.0.1",
    "configure dtc server add web1 host=10.0.0.1 comment=c",
    "configure dtc pool add p1",
    "configure dtc pool add p1 comment=c",
    "configure dtc lbdn add lb1",
    "configure dtc lbdn add lb1 comment=c",
    "configure dtc monitor http add mon1",
    "configure dtc monitor icmp add mon1",
    "configure dtc monitor tcp add mon1",
    "configure dtc topology add t1",
    "configure auth ldap add lab-ldap",
    "configure auth ad add lab-ad",
    "configure auth radius add lab-radius",
    "configure auth tacacs add lab-tacacs",
    "configure auth saml add lab-saml",
    "configure auth certificate add lab-cert",
    "configure admin user add alice password=x",
    "configure admin user add alice password=x comment=c",
    "configure admin group add lab-netops",
    "configure admin role add lab-operator",
    "configure notify endpoint add ep1 uri=https://x",
    "configure notify rule add r1 endpoint=ep1",
    "configure discovery add disc1",
    "configure upgrade group add grp1",
    "configure template network add tmpl1",
    'configure grid attribute add "DC Location" type string',
    "configure ea definition add MyEA type=string",
    # Show with name/filter args (exercises the param-binding code path).
    "show zone probe.example.com",
    "show zone probe.example.com view=External",
    "show network 10.0.0.0/24",
    "show network 10.0.0.0/24 view=External",
    "show record host web01.probe.example.com",
    "show rpz zone rpz.example.com",
    "show rpz record a zone rpz.example.com",
    "show address 10.0.0.1",
    "show views External",
    "show grid Migration",
]


@pytest.mark.parametrize("cmd", _COMMANDS)
async def test_command_runs_with_connected_empty_client(cmd):
    """Each command executes without raising against a permissive mock."""
    async with make_client(_permissive_handler) as client:
        ctx = Context(client=client, online=True, host="grid.test")
        await process_line(cmd, ctx)
