---
hide:
  - navigation
  - toc
---

# ibcli

<div class="hero" markdown>

## An async Python CLI for Infoblox NIOS

Tab-completion at every position, a live REPL, batch mode, and **1,063 commands** over the WAPI.
A ground-up rewrite of the original Perl `ibcli`, with no Perl runtime and no unmaintained SDK.

[Get started](getting-started/index.md){ .md-button .md-button--primary }
[Browse the commands](commands/index.md){ .md-button }

</div>

```console
admin@gm.corp.example > co z a example.com          # tab-expands to: configure zone add
admin@gm.corp.example > configure zone add example.com view=Internal
  OK: configure zone add example.com view Internal
admin@gm.corp.example > show zone example.com
fqdn=example.com view=Internal
```

---

## Why this port exists

The original Perl `ibcli` is roughly 13,000 lines, predates the modern NIOS WAPI, and depends on the `Infoblox::*` Perl
SDK, which is no longer maintained.

<div class="grid cards" markdown>

- **Speaks WAPI directly**

    ---

    REST over [`ibx-nios-sdk`](https://github.com/Infoblox-PS/ibx-nios-sdk). No Perl runtime, no legacy SDK, and async
    end-to-end so a slow grid-wide call never blocks the prompt.

- **The UX network engineers expect**

    ---

    Cisco-IOS-style prefix abbreviation at every position, with inline descriptions in the completion dropdown. `co z a`
    expands to `configure zone add`.

- **Scriptable three ways**

    ---

    `-e` for one-shot, a batch file for bulk change, and `.ibcli.cf` for silent auto-connect. `-i` makes a re-run after
    a partial failure safe.

- **Runs anywhere Python does**

    ---

    Python 3.11 or newer, Windows included. Persistent history in `~/.ibcli_history`, up-arrow recall and `Ctrl-R`
    reverse search.

</div>

---

## Quick start

Install the SDK prerequisite, then the CLI:

```bash
pip install 'ibx-nios-sdk @ git+https://github.com/Infoblox-PS/ibx-nios-sdk@v0.2.0'
pip install ibcli
```

Connect to a grid. Most NIOS deployments use a self-signed certificate, so `-k` is usually needed:

```bash
ibcli -k -s gm.corp.example -u admin -p 'password'
```

Press ++tab++ to explore. Every keyword abbreviates to its shortest unambiguous prefix.

[Full installation guide](getting-started/installation.md){ .md-button }

---

## What it covers

<div class="grid cards" markdown>

- **DNS**

    ---

    Authoritative, forward, stub and delegated zones, forward and reverse. A, AAAA, CNAME, MX, TXT, PTR, SRV, CAA,
    NAPTR, TLSA, HTTPS, SVCB, DNAME and ALIAS records. Host records, shared record groups, RPZ, DNS64, GSS-TSIG.

- **IPAM**

    ---

    Network views, VLAN views, ranges and VLANs. Superhosts, bulkhosts, RIR organisations, hostname policies, and IPv4
    and IPv6 address inventory.

- **DHCP**

    ---

    Networks and containers (v4 and v6), shared networks, ranges, fixed addresses and failover pairs. All five filter
    types, option spaces and definitions, templates, and leases.

- **Grid**

    ---

    Members both pre-provisioned and online, HA pairs with VRRP, MGMT and LAN2 ports, VLAN tagging, port redundancy, NS
    groups, upgrade groups and restart status.

- **Security**

    ---

    Admin users, groups and roles. Auth services for LDAP, AD, RADIUS, TACACS+, SAML and certificates. Approval
    workflows, HSM groups, parental controls and CA certificates.

- **DTC and Ops**

    ---

    DTC servers, pools, LBDNs, monitors and topology rules. CSV import and export, grid backup and restore, support
    bundles, notification rules and outbound integrations.

</div>

[Commands cookbook](commands/cookbook.md){ .md-button .md-button--primary }
[Operator playbook](commands/playbook.md){ .md-button }

---

## Verified, not just written

<div class="grid cards" markdown>

- **3,275 unit tests**

    ---

    Run in under ten seconds against a mocked WAPI using `httpx.MockTransport`. No grid required, so the suite runs in
    CI on every push across Python 3.11, 3.12 and 3.13.

- **Live-grid sweep**

    ---

    `scripts/sweep-show.sh` runs every no-arg `show` command against a real grid and sorts each failure into
    friendly-usage, grid-config, or suspected bug.

- **Smoke harness**

    ---

    `scripts/smoke/` builds, verifies and tears down roughly 10,000 objects across 30-plus types on a real grid,
    including HA pairs and port-redundant members.

- **Integration contracts**

    ---

    A suite gated on `IBCLI_TEST_GRID` pins the NIOS behaviours a mock cannot reproduce, such as licence case
    sensitivity and dict-versus-string ref returns.

</div>

See [Real Grid Status](reference/real-grid-status.md) for the current verification matrix.

---

## Where to go next

<div class="grid cards" markdown>

- [**Getting Started**](getting-started/index.md)

    ---

    Installation, your first connection, and a tour of tab completion.

- [**User Guide**](user-guide/index.md)

    ---

    Invocation modes, the REPL, aliases, batch files and extensible attributes.

- [**Commands**](commands/index.md)

    ---

    Per-domain reference, plus the cookbook and operator playbook.

- [**Reference**](reference/index.md)

    ---

    WAPI object mapping, parser internals, CLI flags and troubleshooting.

- [**Development**](development/index.md)

    ---

    Architecture, adding a command, and the testing workflow.

- [**About**](about/license.md)

    ---

    Licence, third-party dependencies and credits.

</div>
