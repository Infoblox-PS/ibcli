# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""DHCP slice 3a - DHCP ranges and fixed addresses.

Command shapes:
  configure network <n.n.n.n/mm> range add <ip> <ip>
      [comment=<comment> | member=<ip> | failover=<name> | view=<name>]
  configure network <n.n.n.n/mm> range delete <ip> <ip>  [view=<name>]
  show range  [<n.n.n.n/mm>]

  configure network <n.n.n.n/mm> fixed add <ip> <mac>
      [name=<name> | comment=<comment> | view=<name>]
  configure network <n.n.n.n/mm> fixed delete <ip>  [view=<name>]
  show fixed  [<ip>]
"""

from __future__ import annotations

import re

from ibcli.context import Context
from ibcli.registry import command, register
from ibcli.utils import (
    as_dict,
    format_extra_field,
    normalize_cidr,
    normalize_cidr_any,
    parse_extra_fields,
)

# ---------------------------------------------------------------------------
# Helpers (duplicated from network.py to keep modules independent)
# ---------------------------------------------------------------------------


def _parse_kv_all(line: str, key: str) -> list[str]:
    """Match `key value` or `key "quoted value"` repeatedly; return values."""
    pat = rf'\b{re.escape(key)}[= ]+(?:"([^"]+)"|(\S+))'
    return [m[0] or m[1] for m in re.findall(pat, line)]


def _parse_kv(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_comment(line: str) -> str | None:
    m = re.search(r'\bcomment\s+"([^"]+)"', line)
    if m:
        return m.group(1)
    m = re.search(r"\bcomment\s+(\S+)", line)
    return m.group(1) if m else None


def _parse_filter_match(line: str) -> str | None:
    """Parse repeatable ``match=<opt_name>:<value>`` into a NIOS match expression.

    NIOS option filters distinguish two concepts:

    * ``option_list`` - DHCP options the filter *serves* when a client
      matches. These are option **definitions**, populated by the ``rule=``
      keyword elsewhere.
    * ``expression`` - the boolean **match rule** that decides which
      clients the filter applies to. It uses a NIOS-specific mini-grammar,
      e.g. ``option vendor-class-identifier = "ArubaAP"``.

    A filter imported by downstream tools (UDDI / CSP's global-csv import)
    that has only ``option_list`` and no ``expression`` triggers the 400
    ``"Rule list must contain at least one rule value or a list."`` error
    even when NIOS itself accepts the object - the importer treats
    ``apply_as_class=True`` + ``option_list`` as an implicit rule but
    UDDI/CSP does not. Giving each filter an explicit expression makes
    the object round-trip cleanly across both.

    Format: ``match=<option_name>:<value>``. The value may be double-quoted
    to embed whitespace. Multiple ``match=`` keywords are AND-joined.
    Examples::

        match=vendor-class-identifier:ArubaAP
        match=vendor-class-identifier:"MSFT 5.0"
        match=host-name:myhost match=vendor-class-identifier:ArubaAP

    Returns the combined expression string, or ``None`` when no ``match=``
    keyword is present on *line*.
    """
    pat = re.compile(
        r"\bmatch[= ]+"
        r'([^\s:"]+)'  # option name
        r":"
        r'(?:"([^"]*)"|([^\s]+))'  # value (quoted or unquoted to whitespace)
    )
    clauses: list[str] = []
    for m in pat.finditer(line):
        name = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        # Always emit the value double-quoted per NIOS's match-rule grammar.
        clauses.append(f'option {name} = "{value}"')
    if not clauses:
        return None
    # NIOS accepts parenthesised conjuncts; " and " joins cleanly for >1.
    return " and ".join(clauses) if len(clauses) > 1 else clauses[0]


def _parse_filter_rules(line: str) -> list[dict]:
    """Parse repeatable ``rule=<opt_name>:<value>[:<num>]`` into option_list entries.

    NIOS rejects a DHCP option filter (v4 or v6) that has no ``option_list``
    and no ``expression`` with ``"Rule list must contain at least one rule
    value or a list."`` This helper gives the CLI a lightweight way to attach
    rules without requiring callers to write WAPI JSON or the full match-
    expression grammar.

    Format: ``rule=<option_name>:<value>[:<num>]``. The value may be quoted
    with double quotes to embed spaces or colons. Examples::

        rule=vendor-class-identifier:MSFT
        rule=vendor-class-identifier:"MSFT 5.0":60
        rule=host-name:myhost

    Returns a list shaped like WAPI's ``option_list`` (``dhcpoption``): each
    entry has ``name`` and ``value`` keys, plus ``num`` when provided.
    """
    entries: list[dict] = []
    # Parse `rule=<name>:<value>[:<num>]` with the value optionally quoted to
    # embed whitespace or colons. The regex captures, in order:
    #   1. name - no whitespace, colon, or quote
    #   2. value - either a double-quoted string OR a run of non-space,
    #      non-colon characters
    #   3. num  - optional trailing :<digits>
    pat = re.compile(
        r"\brule[= ]+"
        r'([^\s:"]+)'  # name
        r":"  # name/value separator
        r'(?:"([^"]*)"|([^\s:]+))'  # value (quoted or unquoted)
        r"(?::(\d+))?"  # optional :num
    )
    for m in pat.finditer(line):
        name = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        num_str = m.group(4)
        entry: dict = {"name": name, "value": value}
        if num_str is not None:
            entry["num"] = int(num_str)
        entries.append(entry)
    return entries


def _normalize_mac(mac: str) -> str:
    """Insert colons every 2 chars if the MAC string contains no colons."""
    if ":" not in mac:
        # strip any existing separators and re-insert colons
        cleaned = re.sub(r"[^0-9a-fA-F]", "", mac)
        mac = ":".join(cleaned[i : i + 2] for i in range(0, len(cleaned), 2))
    return mac.lower()


async def _find_range_ref(
    ctx: Context,
    start_addr: str,
    end_addr: str,
    view: str | None,
) -> tuple[str, dict] | None:
    """Return (_ref, record) for the matching range, or None."""
    params: dict = {"start_addr": start_addr, "end_addr": end_addr}
    if view:
        params["network_view"] = view
    results = [as_dict(r) async for r in ctx.client.dhcp.range.list(**params)]
    if not results:
        return None
    return (results[0]["_ref"], results[0])


async def _find_fixed_ref(
    ctx: Context,
    ip: str,
    view: str | None,
) -> tuple[str, dict] | None:
    """Return (_ref, record) for the matching fixed address, or None."""
    params: dict = {"ipv4addr": ip}
    if view:
        params["network_view"] = view
    results = [as_dict(r) async for r in ctx.client.dhcp.fixedaddress.list(**params)]
    if not results:
        return None
    return (results[0]["_ref"], results[0])


# ---------------------------------------------------------------------------
# Waypoints - ranges
# ---------------------------------------------------------------------------

# Seed the top-level 'configure' and 'configure network' waypoints with the
# words this module contributes.  network.py normally owns these entries; when
# it is not loaded (e.g. isolated unit tests) dhcp.py must register them itself
# so the dispatcher can resolve the command tree.
register(
    "configure",
    words="network template option_space optiondef",
    help="Create, modify or delete grid objects.",
)
register(
    "configure network",
    words="<n.n.n.n/mm> macfilter filter failover",
    help="IPv4/IPv6 networks, ranges, fixed addresses, filters.",
)
register(
    "show",
    words="range fixed template network lease",
    help="Read grid state without modifying anything.",
)

# Extend the already-registered "configure network <n.n.n.n/mm>" node.
register("configure network <n.n.n.n/mm>", words="range fixed")

register("configure network <n.n.n.n/mm> range", words="add delete")
register("configure network <n.n.n.n/mm> range", words="add delete modify")
register("configure network <n.n.n.n/mm> range add", words="<ip>")
register("configure network <n.n.n.n/mm> range add <ip>", words="<ip>")
register("configure network <n.n.n.n/mm> range modify", words="<ip>")
register("configure network <n.n.n.n/mm> range modify <ip>", words="<ip>")
register(
    "configure network <n.n.n.n/mm> range add <ip> <ip>",
    words="<cr> comment=<comment>|member=<ip>|failover=<name>|view=<name>",
)

register("configure network <n.n.n.n/mm> range delete", words="<ip>")
register("configure network <n.n.n.n/mm> range delete <ip>", words="<ip>")
register(
    "configure network <n.n.n.n/mm> range delete <ip> <ip>",
    words="<cr> view=<name>",
)

# show range
register("show", words="range", help="Read grid state without modifying anything.")
register("show range", words="<cr> <n.n.n.n/mm>", help="DHCP ranges.")
register("show range <n.n.n.n/mm>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - fixed addresses
# ---------------------------------------------------------------------------

register("configure network <n.n.n.n/mm> fixed", words="add delete")
register("configure network <n.n.n.n/mm> fixed add", words="<ip>")
register("configure network <n.n.n.n/mm> fixed add <ip>", words="<mac>")
register(
    "configure network <n.n.n.n/mm> fixed add <ip> <mac>",
    words="<cr> name=<name>|comment=<comment>|view=<name>",
)

register("configure network <n.n.n.n/mm> fixed delete", words="<ip>")
register(
    "configure network <n.n.n.n/mm> fixed delete <ip>",
    words="<cr> view=<name>",
)

# show fixed
register("show", words="fixed", help="Read grid state without modifying anything.")
register("show fixed", words="<cr> <ip>", help="DHCP fixed-address reservations.")
register("show fixed <ip>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> range add <startip> <endip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> range add <ip> <ip>",
    words="<cr> comment=<comment>|member=<ip>|failover=<name>|view=<name>",
    help="Add a DHCP range to a network.",
)
async def cli_add_range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    # Extract CIDR and two IPs from the command line.
    # Pattern: "network <cidr> range add <startip> <endip>"
    m = re.search(r"\bnetwork\s+(\S+)\s+range\s+add\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: CIDR, start IP, and end IP required")
        return
    try:
        cidr = normalize_cidr(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    start_addr = m.group(2)
    end_addr = m.group(3)

    body: dict = {
        "network": cidr,
        "start_addr": start_addr,
        "end_addr": end_addr,
    }

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view

    # failover takes precedence over member
    failover = _parse_kv(line, "failover")
    if failover:
        body["failover_association"] = failover
    else:
        member = _parse_kv(line, "member")
        if member:
            body["member"] = {"_struct": "dhcpmember", "ipv4addr": member}

    await ctx.client.dhcp.range.create(body)


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> range modify <startip> <endip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> range modify <ip> <ip>",
    words="<cr> comment=<comment>|member=<ip>|failover=<name>|view=<name>|clear_failover",
    help=(
        "Modify a DHCP range in place. "
        "Swap to a new failover group with failover=<name> (members come "
        "from the group), or switch back to single-member with member=<ip>."
    ),
)
async def cli_modify_range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+\S+\s+range\s+modify\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: start IP and end IP required")
        return
    start_addr = m.group(1)
    end_addr = m.group(2)
    view = _parse_kv(line, "view")

    found = await _find_range_ref(ctx, start_addr, end_addr, view)
    if found is None:
        print(f"  No range found: {start_addr} - {end_addr}")
        return
    ref, _ = found

    update: dict = {}

    comment = _parse_comment(line)
    if comment:
        update["comment"] = comment

    # failover takes precedence; "member=" switches to a single-member range.
    # A bare "clear_failover" drops the failover association (the server will
    # return an error unless member= is also supplied, since a range must be
    # bound to either).
    failover = _parse_kv(line, "failover")
    member = _parse_kv(line, "member")
    if failover:
        update["failover_association"] = failover
        # NIOS re-pins failover peers from the group, overriding `member`.
    elif member:
        update["member"] = {"_struct": "dhcpmember", "ipv4addr": member}
        update["failover_association"] = ""
    elif re.search(r"\bclear_failover\b", line):
        update["failover_association"] = ""

    if not update:
        print("  Error: nothing to modify (set comment/member/failover)")
        return

    await ctx.client.dhcp.range.update(ref, update)


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> range delete <startip> <endip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> range delete <ip> <ip>",
    words="<cr> view=<name>",
    help="Delete a DHCP range.",
)
async def cli_delete_range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+\S+\s+range\s+delete\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: start IP and end IP required")
        return
    start_addr = m.group(1)
    end_addr = m.group(2)
    view = _parse_kv(line, "view")

    found = await _find_range_ref(ctx, start_addr, end_addr, view)
    if found is None:
        print(f"  No range found: {start_addr} - {end_addr}")
        return
    ref, _ = found

    await ctx.client.dhcp.range.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show range [<cidr>]
# ---------------------------------------------------------------------------


@command("show range", words="<cr> <n.n.n.n/mm>", help="List DHCP ranges.")
@command(
    "show range <n.n.n.n/mm>",
    words="<cr> fields=<field1,field2,...>",
    help="List DHCP ranges in a network.",
)
async def cli_show_range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    cidr = None
    # "show range <cidr>" → tokens[2]
    if len(tokens) >= 3 and "/" in tokens[2]:
        try:
            cidr = normalize_cidr(tokens[2])
        except ValueError as e:
            print(f"  Error: {e}")
            return

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": [
            "network",
            "start_addr",
            "end_addr",
            "comment",
            "failover_association",
            "member",
        ]
        + extra,
    }
    if cidr:
        params["network"] = cidr

    results = [as_dict(r) async for r in ctx.client.dhcp.range.list(**params)]

    for r in results:
        parts = [
            f"network={r.get('network', '')}",
            f"start={r.get('start_addr', '')}",
            f"end={r.get('end_addr', '')}",
        ]
        if r.get("member"):
            mem = r["member"]
            if isinstance(mem, dict):
                parts.append(f"member={mem.get('ipv4addr', mem)}")
            else:
                parts.append(f"member={mem}")
        if r.get("failover_association"):
            parts.append(f"failover={r['failover_association']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> fixed add <ip> <mac>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> fixed add <ip> <mac>",
    words="<cr> name=<name>|comment=<comment>|view=<name>",
    help="Add a fixed (reserved) address.",
)
async def cli_add_fixed(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    # Pattern: "network <cidr> fixed add <ip> <mac>"
    m = re.search(r"\bnetwork\s+\S+\s+fixed\s+add\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: IP and MAC required")
        return
    ip = m.group(1)
    mac = _normalize_mac(m.group(2))

    body: dict = {
        "ipv4addr": ip,
        "mac": mac,
        "match_client": "MAC_ADDRESS",
    }

    name = _parse_kv(line, "name")
    if name:
        body["name"] = name

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view

    await ctx.client.dhcp.fixedaddress.create(body)


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> fixed delete <ip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> fixed delete <ip>",
    words="<cr> view=<name>",
    help="Delete a fixed address.",
)
async def cli_delete_fixed(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+\S+\s+fixed\s+delete\s+(\S+)", line)
    if not m:
        print("  Error: IP required")
        return
    ip = m.group(1)
    view = _parse_kv(line, "view")

    found = await _find_fixed_ref(ctx, ip, view)
    if found is None:
        print(f"  No fixed address found: {ip}")
        return
    ref, _ = found

    await ctx.client.dhcp.fixedaddress.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show fixed [<ip>]
# ---------------------------------------------------------------------------


@command("show fixed", words="<cr> <ip>", help="List fixed addresses.")
@command(
    "show fixed <ip>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific fixed address.",
)
async def cli_show_fixed(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    ip_filter = None
    # "show fixed <ip>" → tokens[2]
    if len(tokens) >= 3:
        candidate = tokens[2]
        # Make sure it's not a keyword like "view" or "fields=..."
        if re.match(r"^\d", candidate) and "=" not in candidate:
            ip_filter = candidate

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["ipv4addr", "mac", "name", "comment", "network"] + extra,
    }
    if ip_filter:
        params["ipv4addr"] = ip_filter

    results = [as_dict(r) async for r in ctx.client.dhcp.fixedaddress.list(**params)]

    for r in results:
        parts = [
            f"network={r.get('network', '')}",
            f"ip={r.get('ipv4addr', '')}",
            f"mac={r.get('mac', '')}",
        ]
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Slice 3b - Fixed-address templates & MAC filters
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper: find a filtermac ref by name
# ---------------------------------------------------------------------------


async def _find_filtermac_ref(
    ctx: Context,
    name: str,
) -> tuple[str, dict] | None:
    """Return (_ref, record) for the named MAC filter, or None."""
    results = [as_dict(r) async for r in ctx.client.dhcp.filtermac.list(name=name)]
    if not results:
        return None
    return (results[0]["_ref"], results[0])


# ---------------------------------------------------------------------------
# Waypoints - fixed-address templates
# ---------------------------------------------------------------------------

register(
    "configure template",
    words="fixed",
    help="DHCP network/range/fixed templates (for provisioning).",
)
register("configure template fixed", words="add delete", help="Fixed-address templates.")
register("configure template fixed add", words="<name>")
register(
    "configure template fixed add <name>",
    words="<cr> offset=<num>|comment=<comment>",
)
register("configure template fixed delete", words="<name>")
register("configure template fixed delete <name>", words="<cr>")

# show template fixed
register(
    "show template", words="fixed", help="DHCP templates (network/range/fixed + IPv6 variants)."
)
register("show template fixed", words="<cr> <name>")
register("show template fixed <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - MAC filters and MAC filter addresses
# ---------------------------------------------------------------------------

register(
    "configure network",
    words="macfilter filter",
    help="IPv4/IPv6 networks, ranges, fixed addresses, filters.",
)
register("configure network macfilter", words="add delete", help="MAC-address DHCP filter lists.")
register("configure network macfilter add", words="<name>")
register("configure network macfilter add <name>", words="<cr>")
register("configure network macfilter delete", words="<name>")
register("configure network macfilter delete <name>", words="<cr>")

register(
    "configure network filter",
    words="<name>",
    help="Populate a MAC filter with specific MAC addresses.",
)
register("configure network filter <name>", words="add delete")
register("configure network filter <name> add", words="macaddress")
register("configure network filter <name> add macaddress", words="<mac>")
register(
    "configure network filter <name> add macaddress <mac>",
    words="<cr> comment=<comment>",
)
register("configure network filter <name> delete", words="macaddress")
register("configure network filter <name> delete macaddress", words="<mac>")
register(
    "configure network filter <name> delete macaddress <mac>",
    words="<cr>",
)

# show network filter
register(
    "show network",
    words="filter",
    help="Networks, network containers, shared networks (IPv4/IPv6).",
)
register("show network filter", words="<cr> <name>")
register("show network filter <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure template fixed add <name>
# ---------------------------------------------------------------------------


@command(
    "configure template fixed add <name>",
    words="<cr> offset=<num>|comment=<comment>",
    help="Add a fixed-address template.",
)
async def cli_add_fixed_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate fixed add\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    body: dict = {"name": name, "number_of_addresses": 1}

    offset_match = re.search(r"\boffset\s+(\d+)", line)
    if offset_match:
        body["offset"] = int(offset_match.group(1))

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.fixedaddresstemplate.create(body)


# ---------------------------------------------------------------------------
# Handler: configure template fixed delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure template fixed delete <name>",
    words="<cr>",
    help="Delete a fixed-address template.",
)
async def cli_delete_fixed_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate fixed delete\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.fixedaddresstemplate.list(name=name)]
    if not results:
        print(f"  No template found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dhcp.fixedaddresstemplate.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show template fixed [<name>]
# ---------------------------------------------------------------------------


@command("show template fixed", words="<cr> <name>", help="List fixed-address templates.")
@command(
    "show template fixed <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific fixed-address template.",
)
async def cli_show_fixed_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    tpl_name = None
    # "show template fixed [<name>]" → name at tokens[3] if present
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<") and "=" not in candidate:
            tpl_name = candidate

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["name", "comment", "offset", "number_of_addresses"] + extra,
    }
    if tpl_name:
        params["name"] = tpl_name

    results = [as_dict(r) async for r in ctx.client.dhcp.fixedaddresstemplate.list(**params)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("offset") is not None:
            parts.append(f"offset={r['offset']}")
        if r.get("number_of_addresses") is not None:
            parts.append(f"num={r['number_of_addresses']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure network macfilter add <name>
# ---------------------------------------------------------------------------


@command(
    "configure network macfilter add <name>",
    words="<cr>",
    help="Create a new MAC filter.",
)
async def cli_add_macfilter(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmacfilter add\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    await ctx.client.dhcp.filtermac.create({"name": name})


# ---------------------------------------------------------------------------
# Handler: configure network macfilter delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure network macfilter delete <name>",
    words="<cr>",
    help="Delete a MAC filter.",
)
async def cli_delete_macfilter(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bmacfilter delete\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    found = await _find_filtermac_ref(ctx, name)
    if found is None:
        print(f"  No MAC filter found: {name}")
        return
    ref, _ = found

    await ctx.client.dhcp.filtermac.delete(ref)


# ---------------------------------------------------------------------------
# Handler: configure network filter <name> add macaddress <mac>
# ---------------------------------------------------------------------------


@command(
    "configure network filter <name> add macaddress <mac>",
    words="<cr> comment=<comment>",
    help="Add a MAC address to a filter.",
)
async def cli_add_macfilteraddr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter\s+(\S+)\s+add\s+macaddress\s+(\S+)", line)
    if not m:
        print("  Error: filter name and MAC required")
        return
    filter_name = m.group(1)
    mac = _normalize_mac(m.group(2))

    # Resolve filter (name is the server-side key, not _ref)
    found = await _find_filtermac_ref(ctx, filter_name)
    if found is None:
        print(f"  No MAC filter found: {filter_name}")
        return

    body: dict = {"mac": mac, "filter": filter_name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.macfilteraddress.create(body)


# ---------------------------------------------------------------------------
# Handler: configure network filter <name> delete macaddress <mac>
# ---------------------------------------------------------------------------


@command(
    "configure network filter <name> delete macaddress <mac>",
    words="<cr>",
    help="Remove a MAC address from a filter.",
)
async def cli_delete_macfilteraddr(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter\s+(\S+)\s+delete\s+macaddress\s+(\S+)", line)
    if not m:
        print("  Error: filter name and MAC required")
        return
    filter_name = m.group(1)
    mac = _normalize_mac(m.group(2))

    # Resolve filter ref
    found = await _find_filtermac_ref(ctx, filter_name)
    if found is None:
        print(f"  No MAC filter found: {filter_name}")
        return
    filter_ref, _ = found

    results = [
        as_dict(r) async for r in ctx.client.dhcp.macfilteraddress.list(mac=mac, filter=filter_ref)
    ]
    if not results:
        print(f"  No MAC filter address found: {mac} in {filter_name}")
        return
    addr_ref = results[0]["_ref"]
    await ctx.client.dhcp.macfilteraddress.delete(addr_ref)


# ---------------------------------------------------------------------------
# Handler: show network filter [<name>]
# ---------------------------------------------------------------------------


@command(
    "show network filter",
    words="<cr> <name>",
    help="List MAC filters.",
)
@command(
    "show network filter <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show MAC addresses in a filter.",
)
async def cli_show_network_filter(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    filter_name = None
    # "show network filter [<name>]" → tokens[3] if present and not a keyword
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        filter_name = tokens[3]

    extra = parse_extra_fields(line)
    if filter_name is None:
        # List all filters
        results = [
            as_dict(r)
            async for r in ctx.client.dhcp.filtermac.list(
                return_fields_plus=["name", "comment"] + extra
            )
        ]
        for r in results:
            parts = [f"name={r.get('name', '')}"]
            if r.get("comment"):
                parts.append(f"comment={r['comment']}")
            print(" ".join(parts))
            for f in extra:
                val = r.get(f)
                if val in (None, "", [], {}):
                    continue
                print(f"  {f}: {format_extra_field(val)}")
    else:
        # Find filter ref, then list MAC addresses
        found = await _find_filtermac_ref(ctx, filter_name)
        if found is None:
            print(f"  No MAC filter found: {filter_name}")
            return
        filter_ref, _ = found
        results = [
            as_dict(r)
            async for r in ctx.client.dhcp.macfilteraddress.list(
                filter=filter_ref,
                return_fields_plus=["mac", "comment"] + extra,
            )
        ]
        for r in results:
            parts = [f"mac={r.get('mac', '')}"]
            if r.get("comment"):
                parts.append(f"comment={r['comment']}")
            print(" ".join(parts))
            for f in extra:
                val = r.get(f)
                if val in (None, "", [], {}):
                    continue
                print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Slice 3c - Failover associations, option definitions, and leases
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - failover
# ---------------------------------------------------------------------------

register(
    "configure network",
    words="failover",
    help="IPv4/IPv6 networks, ranges, fixed addresses, filters.",
)
register("configure network failover", words="add delete", help="DHCP failover peer associations.")
register("configure network failover add", words="<name>")
register("configure network failover add <name>", words="primary")
# primary/secondary identify grid members by host_name (FQDN), not by IP -
# NIOS resolves failover members by name.
register("configure network failover add <name> primary", words="<name>")
register("configure network failover add <name> primary <name>", words="secondary")
register("configure network failover add <name> primary <name> secondary", words="<name>")
register(
    "configure network failover add <name> primary <name> secondary <name>",
    words="<cr>",
)
register("configure network failover delete", words="<name>")
register("configure network failover delete <name>", words="<cr>")

# show network failover / options
register(
    "show network",
    words="failover options",
    help="Networks, network containers, shared networks (IPv4/IPv6).",
)
register("show network failover", words="<cr> <name>")
register("show network failover <name>", words="<cr> fields=<field1,field2,...>")
register("show network options", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - option space and option def
# ---------------------------------------------------------------------------

register("configure", words="option_space optiondef", help="Create, modify or delete grid objects.")
register(
    "configure option_space",
    words="add <name>",
    help="DHCP option spaces (custom vendor/encapsulated option spaces).",
)
register("configure option_space add", words="<name>")
register("configure option_space add <name>", words="<cr>")
register("configure option_space <name>", words="delete")
register("configure option_space <name> delete", words="<cr>")

register(
    "configure optiondef",
    words="add",
    help="DHCP option-code definitions (numeric code → name + type).",
)
register("configure optiondef add", words="<name>")
register("configure optiondef add <name>", words="code")
register("configure optiondef add <name> code", words="<num>")
register("configure optiondef add <name> code <num>", words="type")
register("configure optiondef add <name> code <num> type", words="<name>")
register(
    "configure optiondef add <name> code <num> type <name>",
    words="<cr> space=<name>",
)

# show lease
register("show", words="lease", help="Read grid state without modifying anything.")
register("show lease", words="<cr> <ip>", help="Current DHCP leases.")
register("show lease <ip>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure network failover add <name> primary <fqdn> secondary <fqdn>
# ---------------------------------------------------------------------------


@command(
    "configure network failover add <name> primary <name> secondary <name>",
    words="<cr>",
    help="Create a DHCP failover association between two grid members (by host_name).",
)
async def cli_add_failover(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfailover add\s+(\S+)\s+primary\s+(\S+)\s+secondary\s+(\S+)", line)
    if not m:
        print("  Error: name, primary FQDN, and secondary FQDN required")
        return
    name = m.group(1)
    primary = m.group(2)
    secondary = m.group(3)

    # For primary_server_type=GRID, `primary`/`secondary` are the member's
    # host_name (FQDN) as a plain string.  NIOS resolves the member by name
    # - an IP here will be rejected with "Member <ip> was not found".  The
    # struct form is for server_type=EXTERNAL (not supported yet).
    body: dict = {
        "name": name,
        "primary_server_type": "GRID",
        "secondary_server_type": "GRID",
        "primary": primary,
        "secondary": secondary,
    }

    await ctx.client.dhcp.dhcpfailover.create(body)


# ---------------------------------------------------------------------------
# Handler: configure network failover delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure network failover delete <name>",
    words="<cr>",
    help="Delete a DHCP failover association.",
)
async def cli_delete_failover(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfailover delete\s+(\S+)", line)
    if not m:
        print("  Error: failover name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.dhcpfailover.list(name=name)]
    if not results:
        print(f"  No failover found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dhcp.dhcpfailover.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show network failover [<name>]
# ---------------------------------------------------------------------------


@command(
    "show network failover",
    words="<cr> <name>",
    help="List DHCP failover associations.",
)
@command(
    "show network failover <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCP failover association. fields=a,b,c requests additional WAPI fields.",
)
async def cli_show_failover(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fail_name = None
    # "show network failover [<name>]" → tokens[3] if present (skip fields=...)
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        fail_name = tokens[3]

    extra = parse_extra_fields(line)
    base_fields = ["name", "primary", "secondary", "comment"]
    params: dict = {"return_fields_plus": base_fields + extra}
    if fail_name:
        params["name"] = fail_name

    results = [as_dict(r) async for r in ctx.client.dhcp.dhcpfailover.list(**params)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("primary"):
            pri = r["primary"]
            if isinstance(pri, dict):
                parts.append(f"primary={pri.get('ipv4addr', pri)}")
        if r.get("secondary"):
            sec = r["secondary"]
            if isinstance(sec, dict):
                parts.append(f"secondary={sec.get('ipv4addr', sec)}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure option_space add <name>
# ---------------------------------------------------------------------------


@command(
    "configure option_space add <name>",
    words="<cr>",
    help="Create a DHCP option space.",
)
async def cli_add_option_space(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\boption_space add\s+(\S+)", line)
    if not m:
        print("  Error: option space name required")
        return
    name = m.group(1)

    await ctx.client.dhcp.dhcpoptionspace.create({"name": name})


@command(
    "configure option_space <name> delete",
    words="<cr>",
    help="Delete a DHCP option space.",
)
async def cli_delete_option_space(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return
    m = re.search(r"\boption_space\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: option space name required")
        return
    name = m.group(1)
    results = [
        as_dict(r) async for r in ctx.client.dhcp.dhcpoptionspace.list(name=name, max_results=1)
    ]
    if not results:
        print(f"  No option space found: {name}")
        return
    await ctx.client.dhcp.dhcpoptionspace.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: configure optiondef add <name> code <num> type <type>
# ---------------------------------------------------------------------------


@command(
    "configure optiondef add <name> code <num> type <name>",
    words="<cr> space=<name>",
    help="Create a DHCP option definition.",
)
async def cli_add_optiondef(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(
        r'\boptiondef add\s+(\S+)\s+code\s+(\d+)\s+type\s+(?:"([^"]+)"|(\S+))',
        line,
    )
    if not m:
        print("  Error: name, code, and type required")
        return
    name = m.group(1)
    code = int(m.group(2))
    otype = m.group(3) or m.group(4)

    body: dict = {"name": name, "code": code, "type": otype}

    space = _parse_kv(line, "space")
    if space:
        body["space"] = space

    await ctx.client.dhcp.dhcpoptiondefinition.create(body)


# ---------------------------------------------------------------------------
# Handler: show network options
# ---------------------------------------------------------------------------


@command(
    "show network options",
    words="<cr> fields=<field1,field2,...>",
    help="List DHCP option definitions.",
)
async def cli_show_network_options(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.dhcp.dhcpoptiondefinition.list(
            return_fields_plus=["name", "code", "type", "space"] + extra,
        )
    ]

    for r in results:
        parts = [
            f"name={r.get('name', '')}",
            f"code={r.get('code', '')}",
            f"type={r.get('type', '')}",
        ]
        if r.get("space"):
            parts.append(f"space={r['space']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: show lease [<ip>]
# ---------------------------------------------------------------------------


@command("show lease", words="<cr> <ip>", help="List DHCP leases.")
@command(
    "show lease <ip>", words="<cr> fields=<field1,field2,...>", help="Show a specific DHCP lease."
)
async def cli_show_lease(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    ip_filter = None
    # "show lease [<ip>]" → tokens[2] if present and looks like an IP
    if len(tokens) >= 3 and re.match(r"^\d", tokens[2]) and "=" not in tokens[2]:
        ip_filter = tokens[2]

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": [
            "address",
            "binding_state",
            "hardware",
            "client_hostname",
        ]
        + extra,
    }
    if ip_filter:
        params["address"] = ip_filter

    results = [as_dict(r) async for r in ctx.client.dhcp.lease.list(**params)]

    for r in results:
        parts = [
            f"address={r.get('address', '')}",
            f"state={r.get('binding_state', '')}",
        ]
        if r.get("hardware"):
            parts.append(f"mac={r['hardware']}")
        if r.get("client_hostname"):
            parts.append(f"hostname={r['client_hostname']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# IPv6 parity - Chunk A: ipv6range CRUD
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers - IPv6 range lookup
# ---------------------------------------------------------------------------


async def _find_ipv6range_ref(
    ctx: Context,
    start_addr: str,
    end_addr: str,
    view: str | None,
) -> tuple[str, dict] | None:
    """Return (_ref, record) for the matching IPv6 range, or None."""
    params: dict = {"start_addr": start_addr, "end_addr": end_addr}
    if view:
        params["network_view"] = view
    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6range.list(**params)]
    if not results:
        return None
    return (results[0]["_ref"], results[0])


# ---------------------------------------------------------------------------
# Waypoints - IPv6 range
# ---------------------------------------------------------------------------

# ipv6range and ipv6fixed live under `configure network <cidr>` (see below),
# not at the top level. Only the truly top-level IPv6 objects get registered
# here.
register(
    "configure",
    words="ipv6optionspace ipv6optiondef ipv6shared",
    help="Create, modify or delete grid objects.",
)
register("configure network <n.n.n.n/mm>", words="ipv6range ipv6fixed")

register("configure network <n.n.n.n/mm> ipv6range", words="add delete")
register("configure network <n.n.n.n/mm> ipv6range add", words="<ipv6>")
register("configure network <n.n.n.n/mm> ipv6range add <ipv6>", words="<ipv6>")
register(
    "configure network <n.n.n.n/mm> ipv6range add <ipv6> <ipv6>",
    words="<cr> comment=<comment>|member=<ipv6>|view=<name>",
)

register("configure network <n.n.n.n/mm> ipv6range delete", words="<ipv6>")
register("configure network <n.n.n.n/mm> ipv6range delete <ipv6>", words="<ipv6>")
register(
    "configure network <n.n.n.n/mm> ipv6range delete <ipv6> <ipv6>",
    words="<cr> view=<name>",
)

# show ipv6range
register("show", words="ipv6range", help="Read grid state without modifying anything.")
register("show ipv6range", words="<cr> <n.n.n.n/mm>", help="IPv6 DHCP ranges.")
register("show ipv6range <n.n.n.n/mm>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> ipv6range add <startip> <endip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> ipv6range add <ipv6> <ipv6>",
    words="<cr> comment=<comment>|member=<ipv6>|view=<name>",
    help="Add a DHCPv6 range to a network.",
)
async def cli_add_ipv6range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+(\S+)\s+ipv6range\s+add\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: CIDR, start IP, and end IP required")
        return
    try:
        cidr, _ = normalize_cidr_any(m.group(1))
    except ValueError as e:
        print(f"  Error: {e}")
        return
    start_addr = m.group(2)
    end_addr = m.group(3)

    body: dict = {
        "network": cidr,
        "start_addr": start_addr,
        "end_addr": end_addr,
    }

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view

    member = _parse_kv(line, "member")
    if member:
        body["member"] = {"_struct": "dhcpmember", "ipv6addr": member}

    await ctx.client.dhcp.ipv6range.create(body)


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> ipv6range delete <startip> <endip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> ipv6range delete <ipv6> <ipv6>",
    words="<cr> view=<name>",
    help="Delete a DHCPv6 range.",
)
async def cli_delete_ipv6range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+\S+\s+ipv6range\s+delete\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: start IP and end IP required")
        return
    start_addr = m.group(1)
    end_addr = m.group(2)
    view = _parse_kv(line, "view")

    found = await _find_ipv6range_ref(ctx, start_addr, end_addr, view)
    if found is None:
        print(f"  No IPv6 range found: {start_addr} - {end_addr}")
        return
    ref, _ = found

    await ctx.client.dhcp.ipv6range.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show ipv6range [<cidr>]
# ---------------------------------------------------------------------------


@command("show ipv6range", words="<cr> <n.n.n.n/mm>", help="List DHCPv6 ranges.")
@command(
    "show ipv6range <n.n.n.n/mm>",
    words="<cr> fields=<field1,field2,...>",
    help="List DHCPv6 ranges in a network.",
)
async def cli_show_ipv6range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    cidr = None
    # "show ipv6range <cidr>" → tokens[2]
    if len(tokens) >= 3 and "/" in tokens[2]:
        try:
            cidr, _ = normalize_cidr_any(tokens[2])
        except ValueError as e:
            print(f"  Error: {e}")
            return

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": [
            "network",
            "start_addr",
            "end_addr",
            "comment",
            "member",
        ]
        + extra,
    }
    if cidr:
        params["network"] = cidr

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6range.list(**params)]

    for r in results:
        parts = [
            f"network={r.get('network', '')}",
            f"start={r.get('start_addr', '')}",
            f"end={r.get('end_addr', '')}",
        ]
        if r.get("member"):
            mem = r["member"]
            if isinstance(mem, dict):
                parts.append(f"member={mem.get('ipv6addr', mem.get('ipv4addr', mem))}")
            else:
                parts.append(f"member={mem}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# IPv6 parity - Chunk B: ipv6fixed CRUD
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper - IPv6 fixed address lookup
# ---------------------------------------------------------------------------


async def _find_ipv6fixed_ref(
    ctx: Context,
    ip: str,
    view: str | None,
) -> tuple[str, dict] | None:
    """Return (_ref, record) for the matching IPv6 fixed address, or None."""
    params: dict = {"ipv6addr": ip}
    if view:
        params["network_view"] = view
    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6fixedaddress.list(**params)]
    if not results:
        return None
    return (results[0]["_ref"], results[0])


# ---------------------------------------------------------------------------
# Waypoints - IPv6 fixed address
# ---------------------------------------------------------------------------

register("configure network <n.n.n.n/mm> ipv6fixed", words="add delete")
register("configure network <n.n.n.n/mm> ipv6fixed add", words="<ipv6>")
register("configure network <n.n.n.n/mm> ipv6fixed add <ipv6>", words="<name>")
register(
    "configure network <n.n.n.n/mm> ipv6fixed add <ipv6> <name>",
    words="<cr> name=<name>|comment=<comment>|view=<name>",
)

register("configure network <n.n.n.n/mm> ipv6fixed delete", words="<ipv6>")
register(
    "configure network <n.n.n.n/mm> ipv6fixed delete <ipv6>",
    words="<cr> view=<name>",
)

# show ipv6fixed
register("show", words="ipv6fixed", help="Read grid state without modifying anything.")
register("show ipv6fixed", words="<cr> <ipv6>", help="IPv6 fixed-address reservations.")
register("show ipv6fixed <ipv6>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> ipv6fixed add <ip> <duid>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> ipv6fixed add <ipv6> <name>",
    words="<cr> name=<name>|comment=<comment>|view=<name>",
    help="Add a DHCPv6 fixed (reserved) address (matched by DUID).",
)
async def cli_add_ipv6fixed(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+\S+\s+ipv6fixed\s+add\s+(\S+)\s+(\S+)", line)
    if not m:
        print("  Error: IPv6 address and DUID required")
        return
    ip = m.group(1)
    duid = m.group(2)

    body: dict = {
        "ipv6addr": ip,
        "duid": duid,
        "match_client": "DUID",
    }

    name = _parse_kv(line, "name")
    if name:
        body["name"] = name

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view

    await ctx.client.dhcp.ipv6fixedaddress.create(body)


# ---------------------------------------------------------------------------
# Handler: configure network <cidr> ipv6fixed delete <ip>
# ---------------------------------------------------------------------------


@command(
    "configure network <n.n.n.n/mm> ipv6fixed delete <ipv6>",
    words="<cr> view=<name>",
    help="Delete a DHCPv6 fixed address.",
)
async def cli_delete_ipv6fixed(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bnetwork\s+\S+\s+ipv6fixed\s+delete\s+(\S+)", line)
    if not m:
        print("  Error: IPv6 address required")
        return
    ip = m.group(1)
    view = _parse_kv(line, "view")

    found = await _find_ipv6fixed_ref(ctx, ip, view)
    if found is None:
        print(f"  No IPv6 fixed address found: {ip}")
        return
    ref, _ = found

    await ctx.client.dhcp.ipv6fixedaddress.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show ipv6fixed [<ip>]
# ---------------------------------------------------------------------------


@command("show ipv6fixed", words="<cr> <ipv6>", help="List DHCPv6 fixed addresses.")
@command(
    "show ipv6fixed <ipv6>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCPv6 fixed address.",
)
async def cli_show_ipv6fixed(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    ip_filter = None
    # "show ipv6fixed <ip>" → tokens[2]
    if len(tokens) >= 3:
        candidate = tokens[2]
        # IPv6 addresses start with a hex digit or colon
        if re.match(r"^[0-9a-fA-F:]", candidate) and "=" not in candidate:
            ip_filter = candidate

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["ipv6addr", "duid", "name", "comment", "network"] + extra,
    }
    if ip_filter:
        params["ipv6addr"] = ip_filter

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6fixedaddress.list(**params)]

    for r in results:
        parts = [
            f"network={r.get('network', '')}",
            f"ip={r.get('ipv6addr', '')}",
            f"duid={r.get('duid', '')}",
        ]
        if r.get("name"):
            parts.append(f"name={r['name']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# IPv6 parity - Chunk C: ipv6fixedaddresstemplate + ipv6rangetemplate
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - IPv6 fixed-address template
# ---------------------------------------------------------------------------

register(
    "configure template",
    words="ipv6fixed ipv6range",
    help="DHCP network/range/fixed templates (for provisioning).",
)
register("configure template ipv6fixed", words="add delete", help="IPv6 fixed-address templates.")
register("configure template ipv6fixed add", words="<name>")
register(
    "configure template ipv6fixed add <name>",
    words="<cr> offset=<num>|comment=<comment>",
)
register("configure template ipv6fixed delete", words="<name>")
register("configure template ipv6fixed delete <name>", words="<cr>")

# show template ipv6fixed
register(
    "show template",
    words="ipv6fixed ipv6range",
    help="DHCP templates (network/range/fixed + IPv6 variants).",
)
register("show template ipv6fixed", words="<cr> <name>")
register("show template ipv6fixed <name>", words="<cr> fields=<field1,field2,...>")

# Waypoints - IPv6 range template
register("configure template ipv6range", words="add delete", help="IPv6 range templates.")
register("configure template ipv6range add", words="<name>")
register(
    "configure template ipv6range add <name>",
    words="<cr> offset=<num>|comment=<comment>",
)
register("configure template ipv6range delete", words="<name>")
register("configure template ipv6range delete <name>", words="<cr>")

# show template ipv6range
register("show template ipv6range", words="<cr> <name>")
register("show template ipv6range <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure template ipv6fixed add <name>
# ---------------------------------------------------------------------------


@command(
    "configure template ipv6fixed add <name>",
    words="<cr> offset=<num>|comment=<comment>",
    help="Add a DHCPv6 fixed-address template.",
)
async def cli_add_ipv6fixed_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate ipv6fixed add\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    body: dict = {"name": name, "number_of_addresses": 1}

    offset_match = re.search(r"\boffset\s+(\d+)", line)
    if offset_match:
        body["offset"] = int(offset_match.group(1))

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.ipv6fixedaddresstemplate.create(body)


# ---------------------------------------------------------------------------
# Handler: configure template ipv6fixed delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure template ipv6fixed delete <name>",
    words="<cr>",
    help="Delete a DHCPv6 fixed-address template.",
)
async def cli_delete_ipv6fixed_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate ipv6fixed delete\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6fixedaddresstemplate.list(name=name)]
    if not results:
        print(f"  No IPv6 fixed template found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dhcp.ipv6fixedaddresstemplate.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show template ipv6fixed [<name>]
# ---------------------------------------------------------------------------


@command(
    "show template ipv6fixed", words="<cr> <name>", help="List DHCPv6 fixed-address templates."
)
@command(
    "show template ipv6fixed <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCPv6 fixed-address template.",
)
async def cli_show_ipv6fixed_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    tpl_name = None
    # "show template ipv6fixed [<name>]" → name at tokens[3] if present
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<") and "=" not in candidate:
            tpl_name = candidate

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["name", "comment", "offset", "number_of_addresses"] + extra,
    }
    if tpl_name:
        params["name"] = tpl_name

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6fixedaddresstemplate.list(**params)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("offset") is not None:
            parts.append(f"offset={r['offset']}")
        if r.get("number_of_addresses") is not None:
            parts.append(f"num={r['number_of_addresses']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure template ipv6range add <name>
# ---------------------------------------------------------------------------


@command(
    "configure template ipv6range add <name>",
    words="<cr> offset=<num>|comment=<comment>",
    help="Add a DHCPv6 range template.",
)
async def cli_add_ipv6range_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate ipv6range add\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    body: dict = {"name": name, "number_of_addresses": 1}

    offset_match = re.search(r"\boffset\s+(\d+)", line)
    if offset_match:
        body["offset"] = int(offset_match.group(1))

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.ipv6rangetemplate.create(body)


# ---------------------------------------------------------------------------
# Handler: configure template ipv6range delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure template ipv6range delete <name>",
    words="<cr>",
    help="Delete a DHCPv6 range template.",
)
async def cli_delete_ipv6range_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate ipv6range delete\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6rangetemplate.list(name=name)]
    if not results:
        print(f"  No IPv6 range template found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dhcp.ipv6rangetemplate.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show template ipv6range [<name>]
# ---------------------------------------------------------------------------


@command("show template ipv6range", words="<cr> <name>", help="List DHCPv6 range templates.")
@command(
    "show template ipv6range <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCPv6 range template.",
)
async def cli_show_ipv6range_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    tpl_name = None
    # "show template ipv6range [<name>]" → name at tokens[3] if present
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<") and "=" not in candidate:
            tpl_name = candidate

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["name", "comment", "offset", "number_of_addresses"] + extra,
    }
    if tpl_name:
        params["name"] = tpl_name

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6rangetemplate.list(**params)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("offset") is not None:
            parts.append(f"offset={r['offset']}")
        if r.get("number_of_addresses") is not None:
            parts.append(f"num={r['number_of_addresses']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# IPv6 parity - Chunk D: ipv6optionspace + ipv6optiondef
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - IPv6 option space and option def
# ---------------------------------------------------------------------------

register("configure ipv6optionspace", words="add", help="IPv6 DHCP option spaces.")
register("configure ipv6optionspace add", words="<name>")
register("configure ipv6optionspace add <name>", words="<cr>")

register("configure ipv6optiondef", words="add", help="IPv6 DHCP option-code definitions.")
register("configure ipv6optiondef add", words="<name>")
register("configure ipv6optiondef add <name>", words="code")
register("configure ipv6optiondef add <name> code", words="<num>")
register("configure ipv6optiondef add <name> code <num>", words="type")
register("configure ipv6optiondef add <name> code <num> type", words="<name>")
register(
    "configure ipv6optiondef add <name> code <num> type <name>",
    words="<cr> space=<name>",
)

# show ipv6 options
register("show", words="ipv6options", help="Read grid state without modifying anything.")
register("show ipv6options", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure ipv6optionspace add <name>
# ---------------------------------------------------------------------------


@command(
    "configure ipv6optionspace add <name>",
    words="<cr>",
    help="Create a DHCPv6 option space.",
)
async def cli_add_ipv6_option_space(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bipv6optionspace add\s+(\S+)", line)
    if not m:
        print("  Error: option space name required")
        return
    name = m.group(1)

    await ctx.client.dhcp.ipv6dhcpoptionspace.create({"name": name})


# ---------------------------------------------------------------------------
# Handler: configure ipv6optiondef add <name> code <num> type <type>
# ---------------------------------------------------------------------------


@command(
    "configure ipv6optiondef add <name> code <num> type <name>",
    words="<cr> space=<name>",
    help="Create a DHCPv6 option definition.",
)
async def cli_add_ipv6_optiondef(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bipv6optiondef add\s+(\S+)\s+code\s+(\d+)\s+type\s+(\S+)", line)
    if not m:
        print("  Error: name, code, and type required")
        return
    name = m.group(1)
    code = int(m.group(2))
    otype = m.group(3)

    body: dict = {"name": name, "code": code, "type": otype}

    space = _parse_kv(line, "space")
    if space:
        body["space"] = space

    await ctx.client.dhcp.ipv6dhcpoptiondefinition.create(body)


# ---------------------------------------------------------------------------
# Handler: show ipv6options
# ---------------------------------------------------------------------------


@command(
    "show ipv6options",
    words="<cr> fields=<field1,field2,...>",
    help="List DHCPv6 option definitions.",
)
async def cli_show_ipv6_options(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    extra = parse_extra_fields(line)
    results = [
        as_dict(r)
        async for r in ctx.client.dhcp.ipv6dhcpoptiondefinition.list(
            return_fields_plus=["name", "code", "type", "space"] + extra,
        )
    ]

    for r in results:
        parts = [
            f"name={r.get('name', '')}",
            f"code={r.get('code', '')}",
            f"type={r.get('type', '')}",
        ]
        if r.get("space"):
            parts.append(f"space={r['space']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# IPv6 parity - Chunk E: ipv6sharednetwork
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - IPv6 shared network
# ---------------------------------------------------------------------------

register(
    "configure ipv6shared",
    words="add delete",
    help="IPv6 shared networks (multiple prefixes served as one pool).",
)
register("configure ipv6shared add", words="<name>")
register(
    "configure ipv6shared add <name>",
    words="<cr> comment=<comment>|view=<name>",
)
register("configure ipv6shared delete", words="<name>")
register("configure ipv6shared delete <name>", words="<cr>")

# show ipv6shared
register("show", words="ipv6shared", help="Read grid state without modifying anything.")
register("show ipv6shared", words="<cr> <name>", help="IPv6 shared networks.")
register("show ipv6shared <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure ipv6shared add <name>
# ---------------------------------------------------------------------------


@command(
    "configure ipv6shared add <name>",
    words="<cr> comment=<comment>|view=<name>",
    help="Create a DHCPv6 shared network.",
)
async def cli_add_ipv6shared(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bipv6shared add\s+(\S+)", line)
    if not m:
        print("  Error: shared network name required")
        return
    name = m.group(1)

    body: dict = {"name": name}

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    view = _parse_kv(line, "view")
    if view:
        body["network_view"] = view

    await ctx.client.dhcp.ipv6sharednetwork.create(body)


# ---------------------------------------------------------------------------
# Handler: configure ipv6shared delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure ipv6shared delete <name>",
    words="<cr>",
    help="Delete a DHCPv6 shared network.",
)
async def cli_delete_ipv6shared(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bipv6shared delete\s+(\S+)", line)
    if not m:
        print("  Error: shared network name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6sharednetwork.list(name=name)]
    if not results:
        print(f"  No IPv6 shared network found: {name}")
        return
    ref = results[0]["_ref"]
    await ctx.client.dhcp.ipv6sharednetwork.delete(ref)


# ---------------------------------------------------------------------------
# Handler: show ipv6shared [<name>]
# ---------------------------------------------------------------------------


@command("show ipv6shared", words="<cr> <name>", help="List DHCPv6 shared networks.")
@command(
    "show ipv6shared <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCPv6 shared network.",
)
async def cli_show_ipv6shared(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    net_name = None
    # "show ipv6shared [<name>]" → tokens[2] if present
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        net_name = tokens[2]

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["name", "comment", "network_view"] + extra,
    }
    if net_name:
        params["name"] = net_name

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6sharednetwork.list(**params)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("network_view"):
            parts.append(f"view={r['network_view']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Phase 10 - Chunk A: DHCP filters
# (filterfingerprint, filternac, filteroption, filterrelayagent, ipv6filteroption)
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - filter fingerprint
# ---------------------------------------------------------------------------

register(
    "configure",
    words="filter fingerprint roaming_host",
    help="Create, modify or delete grid objects.",
)
register(
    "configure filter",
    words="fingerprint nac option relayagent ipv6option",
    help="DHCP request filters (fingerprint/option/nac/relayagent/ipv6option).",
)

register(
    "configure filter fingerprint",
    words="add <name>",
    help="Fingerprint-based DHCP filter (matches client OS/device).",
)
register("configure filter fingerprint add", words="<name>")
register(
    "configure filter fingerprint add <name>",
    words="<cr> comment=<comment>",
)
register("configure filter fingerprint <name>", words="delete")
register("configure filter fingerprint <name> delete", words="<cr>")

register("show", words="filter", help="Read grid state without modifying anything.")
register(
    "show filter",
    words="fingerprint nac option relayagent ipv6option",
    help="DHCP request filters.",
)
register("show filter fingerprint", words="<cr> <name>")
register("show filter fingerprint <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - filter nac
# ---------------------------------------------------------------------------

register(
    "configure filter nac",
    words="add <name>",
    help="NAC integration filter (matches on NAC posture).",
)
register("configure filter nac add", words="<name>")
register(
    "configure filter nac add <name>",
    words="<cr> comment=<comment>",
)
register("configure filter nac <name>", words="delete")
register("configure filter nac <name> delete", words="<cr>")

register("show filter nac", words="<cr> <name>")
register("show filter nac <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - filter option
# ---------------------------------------------------------------------------

register(
    "configure filter option",
    words="add <name>",
    help="DHCP option-based filter (matches on option values).",
)
register("configure filter option add", words="<name>")
register(
    "configure filter option add <name>",
    words="<cr> expression=<name>|rule=<name>|match=<name>|comment=<comment>",
)
register("configure filter option <name>", words="delete")
register("configure filter option <name> delete", words="<cr>")

register("show filter option", words="<cr> <name>")
register("show filter option <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - filter relayagent
# ---------------------------------------------------------------------------

register(
    "configure filter relayagent",
    words="add <name>",
    help="Relay-agent filter (matches option-82 circuit/remote ID).",
)
register("configure filter relayagent add", words="<name>")
register(
    "configure filter relayagent add <name>",
    words="<cr> comment=<comment>|"
    "is_circuit_id=<name>|circuit_id_name=<name>|"
    "is_circuit_id_substring=<name>|"
    "circuit_id_substring_offset=<num>|"
    "circuit_id_substring_length=<num>|"
    "is_remote_id=<name>|remote_id_name=<name>|"
    "is_remote_id_substring=<name>|"
    "remote_id_substring_offset=<num>|"
    "remote_id_substring_length=<num>",
)
register(
    "configure filter relayagent add <name>",
    words="<cr> comment=<comment>",
)
register("configure filter relayagent <name>", words="delete")
register("configure filter relayagent <name> delete", words="<cr>")

register("show filter relayagent", words="<cr> <name>")
register("show filter relayagent <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - filter ipv6option
# ---------------------------------------------------------------------------

register("configure filter ipv6option", words="add <name>", help="IPv6 option-based DHCP filter.")
register("configure filter ipv6option add", words="<name>")
register(
    "configure filter ipv6option add <name>",
    words="<cr> expression=<name>|rule=<name>|match=<name>|comment=<comment>",
)
register("configure filter ipv6option <name>", words="delete")
register("configure filter ipv6option <name> delete", words="<cr>")

register("show filter ipv6option", words="<cr> <name>")
register("show filter ipv6option <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure filter fingerprint add <name>
# ---------------------------------------------------------------------------


@command(
    "configure filter fingerprint add <name>",
    words="<cr> comment=<comment>|fp=<name>",
    help="Create a DHCP fingerprint filter. fp=<name> references an existing "
    "Fingerprint definition (required by WAPI). Repeatable.",
)
async def cli_add_filter_fingerprint(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter fingerprint add\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    fps = _parse_kv_all(line, "fp")
    if fps:
        body["fingerprint"] = fps

    await ctx.client.dhcp.filterfingerprint.create(body)


# ---------------------------------------------------------------------------
# Handler: configure filter fingerprint <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure filter fingerprint <name> delete",
    words="<cr>",
    help="Delete a DHCP fingerprint filter.",
)
async def cli_delete_filter_fingerprint(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter fingerprint\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.filterfingerprint.list(name=name)]
    if not results:
        print(f"  No fingerprint filter found: {name}")
        return
    await ctx.client.dhcp.filterfingerprint.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show filter fingerprint [<name>]
# ---------------------------------------------------------------------------


@command("show filter fingerprint", words="<cr> <name>", help="List DHCP fingerprint filters.")
@command(
    "show filter fingerprint <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific fingerprint filter.",
)
async def cli_show_filter_fingerprint(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fname = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        fname = tokens[3]

    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["name", "comment"] + extra}
    if fname:
        params["name"] = fname

    results = [as_dict(r) async for r in ctx.client.dhcp.filterfingerprint.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure filter nac add <name>
# ---------------------------------------------------------------------------


@command(
    "configure filter nac add <name>",
    words="<cr> comment=<comment>",
    help="Create a DHCP NAC filter.",
)
async def cli_add_filter_nac(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter nac add\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.filternac.create(body)


# ---------------------------------------------------------------------------
# Handler: configure filter nac <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure filter nac <name> delete",
    words="<cr>",
    help="Delete a DHCP NAC filter.",
)
async def cli_delete_filter_nac(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter nac\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.filternac.list(name=name)]
    if not results:
        print(f"  No NAC filter found: {name}")
        return
    await ctx.client.dhcp.filternac.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show filter nac [<name>]
# ---------------------------------------------------------------------------


@command("show filter nac", words="<cr> <name>", help="List DHCP NAC filters.")
@command(
    "show filter nac <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific NAC filter.",
)
async def cli_show_filter_nac(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fname = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        fname = tokens[3]

    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["name", "comment"] + extra}
    if fname:
        params["name"] = fname

    results = [as_dict(r) async for r in ctx.client.dhcp.filternac.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure filter option add <name>
# ---------------------------------------------------------------------------


@command(
    "configure filter option add <name>",
    words="<cr> expression=<name>|rule=<name>|match=<name>|comment=<comment>",
    help="Create a DHCP option filter. Pass expression= for a full match "
    "expression, match=<opt_name>:<value> (repeatable, AND-joined) for "
    "the common equality case, and/or rule=<opt_name>:<value>[:<num>] "
    "(repeatable) to populate option_list. NIOS requires at least one "
    "rule or an expression - creating an empty filter is rejected with "
    "'Rule list must contain at least one rule value or a list.'",
)
async def cli_add_filter_option(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter option add\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    body: dict = {"name": name}

    expr = _parse_kv(line, "expression")
    match_expr = _parse_filter_match(line)
    # match= is a shortcut for the common equality case and is honoured as
    # `expression`. Explicit expression= wins if the user supplied both.
    if expr:
        body["expression"] = expr
    elif match_expr:
        body["expression"] = match_expr

    rules = _parse_filter_rules(line)
    if rules:
        body["option_list"] = rules

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.filteroption.create(body)


# ---------------------------------------------------------------------------
# Handler: configure filter option <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure filter option <name> delete",
    words="<cr>",
    help="Delete a DHCP option filter.",
)
async def cli_delete_filter_option(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter option\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.filteroption.list(name=name)]
    if not results:
        print(f"  No option filter found: {name}")
        return
    await ctx.client.dhcp.filteroption.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show filter option [<name>]
# ---------------------------------------------------------------------------


@command("show filter option", words="<cr> <name>", help="List DHCP option filters.")
@command(
    "show filter option <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific option filter.",
)
async def cli_show_filter_option(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fname = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        fname = tokens[3]

    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["name", "expression", "comment"] + extra}
    if fname:
        params["name"] = fname

    results = [as_dict(r) async for r in ctx.client.dhcp.filteroption.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("expression"):
            parts.append(f"expression={r['expression']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure filter relayagent add <name>
# ---------------------------------------------------------------------------


@command(
    "configure filter relayagent add <name>",
    words="<cr> comment=<comment>|"
    "is_circuit_id=<name>|circuit_id_name=<name>|"
    "is_circuit_id_substring=<name>|"
    "circuit_id_substring_offset=<num>|"
    "circuit_id_substring_length=<num>|"
    "is_remote_id=<name>|remote_id_name=<name>|"
    "is_remote_id_substring=<name>|"
    "remote_id_substring_offset=<num>|"
    "remote_id_substring_length=<num>",
    help="Create a DHCP relay-agent filter. WAPI requires at least one of "
    "is_circuit_id or is_remote_id to be NOT set to ANY; MATCHES_VALUE "
    "additionally needs circuit_id_name / remote_id_name.",
)
async def cli_add_filter_relayagent(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter relayagent add\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    body: dict = {"name": name}
    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment
    for k in (
        "is_circuit_id",
        "circuit_id_name",
        "is_circuit_id_substring",
        "circuit_id_substring_offset",
        "circuit_id_substring_length",
        "is_remote_id",
        "remote_id_name",
        "is_remote_id_substring",
        "remote_id_substring_offset",
        "remote_id_substring_length",
    ):
        v = _parse_kv(line, k)
        if v is not None and v != "":
            # Coerce booleans (WAPI treats is_*_substring as boolean).
            if v.lower() in ("true", "false"):
                v = v.lower() == "true"
            elif v.isdigit():
                v = int(v)
            body[k] = v

    await ctx.client.dhcp.filterrelayagent.create(body)


# ---------------------------------------------------------------------------
# Handler: configure filter relayagent <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure filter relayagent <name> delete",
    words="<cr>",
    help="Delete a DHCP relay-agent filter.",
)
async def cli_delete_filter_relayagent(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter relayagent\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.filterrelayagent.list(name=name)]
    if not results:
        print(f"  No relay-agent filter found: {name}")
        return
    await ctx.client.dhcp.filterrelayagent.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show filter relayagent [<name>]
# ---------------------------------------------------------------------------


@command("show filter relayagent", words="<cr> <name>", help="List DHCP relay-agent filters.")
@command(
    "show filter relayagent <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific relay-agent filter.",
)
async def cli_show_filter_relayagent(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fname = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        fname = tokens[3]

    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["name", "comment"] + extra}
    if fname:
        params["name"] = fname

    results = [as_dict(r) async for r in ctx.client.dhcp.filterrelayagent.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure filter ipv6option add <name>
# ---------------------------------------------------------------------------


@command(
    "configure filter ipv6option add <name>",
    words="<cr> expression=<name>|rule=<name>|match=<name>|comment=<comment>",
    help="Create a DHCPv6 option filter. Pass expression= for a full match "
    "expression, match=<opt_name>:<value> (repeatable, AND-joined) for "
    "the common equality case, and/or rule=<opt_name>:<value>[:<num>] "
    "(repeatable) to populate option_list. NIOS requires at least one "
    "rule or an expression.",
)
async def cli_add_filter_ipv6option(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter ipv6option add\s+(\S+)", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    body: dict = {"name": name}

    expr = _parse_kv(line, "expression")
    match_expr = _parse_filter_match(line)
    if expr:
        body["expression"] = expr
    elif match_expr:
        body["expression"] = match_expr

    rules = _parse_filter_rules(line)
    if rules:
        body["option_list"] = rules

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.ipv6filteroption.create(body)


# ---------------------------------------------------------------------------
# Handler: configure filter ipv6option <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure filter ipv6option <name> delete",
    words="<cr>",
    help="Delete a DHCPv6 option filter.",
)
async def cli_delete_filter_ipv6option(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfilter ipv6option\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: filter name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6filteroption.list(name=name)]
    if not results:
        print(f"  No IPv6 option filter found: {name}")
        return
    await ctx.client.dhcp.ipv6filteroption.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show filter ipv6option [<name>]
# ---------------------------------------------------------------------------


@command("show filter ipv6option", words="<cr> <name>", help="List DHCPv6 option filters.")
@command(
    "show filter ipv6option <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCPv6 option filter.",
)
async def cli_show_filter_ipv6option(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fname = None
    if len(tokens) >= 4 and not tokens[3].startswith("<") and "=" not in tokens[3]:
        fname = tokens[3]

    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["name", "expression", "comment"] + extra}
    if fname:
        params["name"] = fname

    results = [as_dict(r) async for r in ctx.client.dhcp.ipv6filteroption.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("expression"):
            parts.append(f"expression={r['expression']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Phase 10 - Chunk B: fingerprint definitions + roaming hosts
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - fingerprint definitions (distinct from filterfingerprint)
# ---------------------------------------------------------------------------

register(
    "configure fingerprint",
    words="add <name>",
    help="Fingerprint definitions (used by fingerprint filters).",
)
register("configure fingerprint add", words="<name>")
register(
    "configure fingerprint add <name>",
    words="<cr> vendor_id=<name>|comment=<comment>",
)
register("configure fingerprint <name>", words="delete")
register("configure fingerprint <name> delete", words="<cr>")

register("show", words="fingerprint", help="Read grid state without modifying anything.")
register("show fingerprint", words="<cr> <name>", help="DHCP fingerprint definitions.")
register("show fingerprint <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - roaming hosts
# ---------------------------------------------------------------------------

register(
    "configure roaming_host",
    words="add <name>",
    help="Roaming-host DHCP records (follow a client across networks).",
)
register("configure roaming_host add", words="<name>")
register(
    "configure roaming_host add <name>",
    words="<cr> match_client=<name>|comment=<comment>",
)
register("configure roaming_host <name>", words="delete")
register("configure roaming_host <name> delete", words="<cr>")

register("show", words="roaming_host", help="Read grid state without modifying anything.")
register(
    "show roaming_host",
    words="<cr> <name>",
    help="Roaming-host records (laptop leases across networks).",
)
register("show roaming_host <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure fingerprint add <name>
# ---------------------------------------------------------------------------


@command(
    "configure fingerprint add <name>",
    words="<cr> vendor_id=<name>|comment=<comment>",
    help="Create a DHCP fingerprint definition.",
)
async def cli_add_fingerprint(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfingerprint add\s+(\S+)", line)
    if not m:
        print("  Error: fingerprint name required")
        return
    name = m.group(1)

    body: dict = {"name": name}

    vendor = _parse_kv(line, "vendor_id")
    if vendor:
        body["vendor_id"] = [vendor]

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.fingerprint.create(body)


# ---------------------------------------------------------------------------
# Handler: configure fingerprint <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure fingerprint <name> delete",
    words="<cr>",
    help="Delete a DHCP fingerprint definition.",
)
async def cli_delete_fingerprint(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\bfingerprint\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: fingerprint name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.fingerprint.list(name=name)]
    if not results:
        print(f"  No fingerprint found: {name}")
        return
    await ctx.client.dhcp.fingerprint.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show fingerprint [<name>]
# ---------------------------------------------------------------------------


@command("show fingerprint", words="<cr> <name>", help="List DHCP fingerprint definitions.")
@command(
    "show fingerprint <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCP fingerprint.",
)
async def cli_show_fingerprint(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    fname = None
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        fname = tokens[2]

    extra = parse_extra_fields(line)
    params: dict = {"return_fields_plus": ["name", "vendor_id", "comment", "type"] + extra}
    if fname:
        params["name"] = fname

    results = [as_dict(r) async for r in ctx.client.dhcp.fingerprint.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        vendor_id = r.get("vendor_id")
        if vendor_id:
            if isinstance(vendor_id, list):
                parts.append(f"vendor_id={','.join(vendor_id)}")
            else:
                parts.append(f"vendor_id={vendor_id}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: configure roaming_host add <name>
# ---------------------------------------------------------------------------


@command(
    "configure roaming_host add <name>",
    words="<cr> match_client=<name>|comment=<comment>",
    help="Create a DHCP roaming host.",
)
async def cli_add_roaming_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\broaming_host add\s+(\S+)", line)
    if not m:
        print("  Error: roaming host name required")
        return
    name = m.group(1)

    body: dict = {"name": name}

    match_client = _parse_kv(line, "match_client")
    if match_client:
        body["match_client"] = match_client

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.roaminghost.create(body)


# ---------------------------------------------------------------------------
# Handler: configure roaming_host <name> delete
# ---------------------------------------------------------------------------


@command(
    "configure roaming_host <name> delete",
    words="<cr>",
    help="Delete a DHCP roaming host.",
)
async def cli_delete_roaming_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\broaming_host\s+(\S+)\s+delete", line)
    if not m:
        print("  Error: roaming host name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.roaminghost.list(name=name)]
    if not results:
        print(f"  No roaming host found: {name}")
        return
    await ctx.client.dhcp.roaminghost.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show roaming_host [<name>]
# ---------------------------------------------------------------------------


@command("show roaming_host", words="<cr> <name>", help="List DHCP roaming hosts.")
@command(
    "show roaming_host <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific DHCP roaming host.",
)
async def cli_show_roaming_host(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    host_name = None
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        host_name = tokens[2]

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["name", "match_client", "mac", "comment"] + extra,
    }
    if host_name:
        params["name"] = host_name

    results = [as_dict(r) async for r in ctx.client.dhcp.roaminghost.list(**params)]
    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("match_client"):
            parts.append(f"match_client={r['match_client']}")
        if r.get("mac"):
            parts.append(f"mac={r['mac']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ===========================================================================
# Phase 10 - Chunk C: range template + ordered_range + dhcp_statistics
# ===========================================================================

# ---------------------------------------------------------------------------
# Waypoints - IPv4 range template (v4 counterpart of ipv6rangetemplate)
# ---------------------------------------------------------------------------

register(
    "configure template",
    words="range",
    help="DHCP network/range/fixed templates (for provisioning).",
)
register("configure template range", words="add delete", help="DHCP range templates.")
register("configure template range add", words="<name>")
register(
    "configure template range add <name>",
    words="<cr> number_of_addresses=<num>|comment=<comment>",
)
register("configure template range delete", words="<name>")
register("configure template range delete <name>", words="<cr>")

register(
    "show template", words="range", help="DHCP templates (network/range/fixed + IPv6 variants)."
)
register("show template range", words="<cr> <name>")
register("show template range <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - ordered ranges (read-only)
# ---------------------------------------------------------------------------

register("show", words="ordered_range", help="Read grid state without modifying anything.")
register(
    "show ordered_range",
    words="<cr> <n.n.n.n/mm>",
    help="DHCP ranges in a network, listed in lookup order.",
)
register("show ordered_range <n.n.n.n/mm>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Waypoints - DHCP statistics (read-only)
# ---------------------------------------------------------------------------

register("show", words="dhcp_statistics", help="Read grid state without modifying anything.")
register(
    "show dhcp_statistics",
    words="<cr> <name>",
    help="DHCP utilization statistics for a member/network.",
)
register("show dhcp_statistics <name>", words="<cr> fields=<field1,field2,...>")


# ---------------------------------------------------------------------------
# Handler: configure template range add <name>
# ---------------------------------------------------------------------------


@command(
    "configure template range add <name>",
    words="<cr> number_of_addresses=<num>|offset=<num>|comment=<comment>",
    help="Create an IPv4 DHCP range template. offset=<n> and "
    "number_of_addresses=<n> together define the range inside the parent "
    "network (both required by WAPI).",
)
async def cli_add_range_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate range add\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    body: dict = {"name": name}

    num_match = re.search(r"\bnumber_of_addresses[= ]+(\d+)", line)
    if num_match:
        body["number_of_addresses"] = int(num_match.group(1))
    offset_match = re.search(r"\boffset[= ]+(\d+)", line)
    if offset_match:
        body["offset"] = int(offset_match.group(1))

    comment = _parse_comment(line)
    if comment:
        body["comment"] = comment

    await ctx.client.dhcp.rangetemplate.create(body)


# ---------------------------------------------------------------------------
# Handler: configure template range delete <name>
# ---------------------------------------------------------------------------


@command(
    "configure template range delete <name>",
    words="<cr>",
    help="Delete an IPv4 DHCP range template.",
)
async def cli_delete_range_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    m = re.search(r"\btemplate range delete\s+(\S+)", line)
    if not m:
        print("  Error: template name required")
        return
    name = m.group(1)

    results = [as_dict(r) async for r in ctx.client.dhcp.rangetemplate.list(name=name)]
    if not results:
        print(f"  No range template found: {name}")
        return
    await ctx.client.dhcp.rangetemplate.delete(results[0]["_ref"])


# ---------------------------------------------------------------------------
# Handler: show template range [<name>]
# ---------------------------------------------------------------------------


@command("show template range", words="<cr> <name>", help="List IPv4 DHCP range templates.")
@command(
    "show template range <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show a specific range template.",
)
async def cli_show_range_template(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    tpl_name = None
    # "show template range [<name>]" → name at tokens[3] if present
    if len(tokens) >= 4:
        candidate = tokens[3]
        if not candidate.startswith("<") and "=" not in candidate:
            tpl_name = candidate

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["name", "comment", "offset", "number_of_addresses"] + extra,
    }
    if tpl_name:
        params["name"] = tpl_name

    results = [as_dict(r) async for r in ctx.client.dhcp.rangetemplate.list(**params)]

    for r in results:
        parts = [f"name={r.get('name', '')}"]
        if r.get("offset") is not None:
            parts.append(f"offset={r['offset']}")
        if r.get("number_of_addresses") is not None:
            parts.append(f"num={r['number_of_addresses']}")
        if r.get("comment"):
            parts.append(f"comment={r['comment']}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: show ordered_range [<network>]
# ---------------------------------------------------------------------------


@command(
    "show ordered_range",
    words="<cr> <n.n.n.n/mm>",
    help="List ordered DHCP ranges.",
)
@command(
    "show ordered_range <n.n.n.n/mm>",
    words="<cr> fields=<field1,field2,...>",
    help="Show ordered DHCP ranges for a network.",
)
async def cli_show_ordered_range(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    network = None
    if len(tokens) >= 3 and "/" in tokens[2]:
        try:
            network = normalize_cidr(tokens[2])
        except ValueError as e:
            print(f"  Error: {e}")
            return

    if not network:
        print("  Error: network required (usage: show ordered_range <n.n.n.n/mm>)")
        return

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": ["network", "ranges"] + extra,
        "network": network,
    }

    results = [as_dict(r) async for r in ctx.client.dhcp.orderedranges.list(**params)]

    for r in results:
        parts = [f"network={r.get('network', '')}"]
        ranges = r.get("ranges") or []
        if ranges:
            parts.append(f"ranges={len(ranges)}")
        print(" ".join(parts))
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")


# ---------------------------------------------------------------------------
# Handler: show dhcp_statistics [<member>]
# ---------------------------------------------------------------------------


@command(
    "show dhcp_statistics",
    words="<cr> <name>",
    help="Show DHCP utilisation statistics.",
)
@command(
    "show dhcp_statistics <name>",
    words="<cr> fields=<field1,field2,...>",
    help="Show DHCP utilisation statistics for a member.",
)
async def cli_show_dhcp_statistics(line: str, ctx: Context) -> None:
    if ctx.client is None:
        print("  Not connected")
        return

    tokens = line.split()
    member = None
    if len(tokens) >= 3 and not tokens[2].startswith("<") and "=" not in tokens[2]:
        member = tokens[2]

    if not member:
        print("  Error: member required (usage: show dhcp_statistics <member>)")
        return

    extra = parse_extra_fields(line)
    params: dict = {
        "return_fields_plus": [
            "dhcp_utilization",
            "dhcp_utilization_status",
            "dynamic_hosts",
            "static_hosts",
            "total_hosts",
        ]
        + extra,
        # WAPI uses 'statistics_object' as the required filter on this endpoint.
        "statistics_object": member,
    }

    results = [as_dict(r) async for r in ctx.client.dhcp.dhcp_statistics.list(**params)]

    for r in results:
        parts = []
        util = r.get("dhcp_utilization")
        if util is not None:
            parts.append(f"utilization={util / 1000:.1f}%")
        status = r.get("dhcp_utilization_status")
        if status:
            parts.append(f"status={status}")
        dynamic = r.get("dynamic_hosts")
        if dynamic is not None:
            parts.append(f"dynamic={dynamic}")
        static = r.get("static_hosts")
        if static is not None:
            parts.append(f"static={static}")
        total = r.get("total_hosts")
        if total is not None:
            parts.append(f"total={total}")
        print(" ".join(parts) if parts else "(no data)")
        for f in extra:
            val = r.get(f)
            if val in (None, "", [], {}):
                continue
            print(f"  {f}: {format_extra_field(val)}")
