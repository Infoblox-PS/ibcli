# Real Grid Verification Status

This page documents which ibcli commands have been verified against a live NIOS grid, and which are mocked-only at the time of writing (April 2026).

## Summary

The test suite passes **3,275 tests** against mocked WAPI responses (via `httpx.MockTransport`). Mocked tests prove
that ibcli sends the HTTP requests it *thinks* are correct - they do not prove that NIOS actually accepts those
requests. The live-grid audit tooling (`scripts/sweep-show.sh` and `scripts/smoke/`) and the integration suite in
`tests/integration/` exist to close that gap.

A real-grid integration suite now lives in `tests/integration/`.  Run it
to get the most accurate up-to-date verification status:

```bash
IBCLI_TEST_GRID=<gm_ip> IBCLI_TEST_USER=admin IBCLI_TEST_PASS=<pass> \
    pytest tests/integration -v
```

See [Testing → Real-grid integration tests](../development/testing.md#real-grid-integration-tests) for full setup instructions.

Real-grid verification requires access to a physical or virtual NIOS appliance.

## Verified commands

The definitive source of truth is now the integration suite.  Run it against
your grid and check the results.  The table below tracks commands that have
been manually confirmed in addition to having automated integration tests.

| Command | Status | Grid | WAPI version | Date |
|---|---|---|---|---|
| `download database <file>` | ✅ VERIFIED | 192.0.2.40 | v2.14 | 2026-04-17 |
| `configure grid <n> member add` (plain) | ✅ integration test | - | - | - |
| `configure grid <n> member add` (pre-provisioned) | ✅ integration test | - | - | - |
| `configure network failover add` | ✅ integration test | - | - | - |
| `configure network add` | ✅ integration test | - | - | - |
| `configure network <cidr> range add` (failover) | ✅ integration test | - | - | - |

!!! note "Debugging story: the 415 fix"
    During initial real-grid testing, `download database` failed with HTTP 415 Unsupported Media Type on the
    `http_direct_file_io` GET (step 2 of the fileop protocol). Apache on NIOS requires the client to send
    `Content-Type: application/force-download` on that request. Without it, Apache rejects the download.

    The header is sent by `stream_download` in `src/ibcli/fileop.py`:

    ```python
    DOWNLOAD_HEADERS = {"Content-Type": "application/force-download"}
    ```

    It originally lived in a pre-SDK `session.py`, was lost when that module
    was removed during the `ibx-nios-sdk` port, and is now covered by a mocked
    test so CI catches its removal.

    **Lesson for future real-grid testing:** Other `http_direct_file_io` operations (log downloads, lease history,
    support bundles) may have similar undocumented header requirements. If you see a 415 on any download command,
    run with `-d 2` to inspect the full request and verify the `Content-Type: application/force-download` header
    is present. See [Troubleshooting](troubleshooting.md#http-415-on-file-downloads) for full details.

## Mocked-only (not yet verified on real grid)

All other commands are mocked-only. The table below lists the main families:

| Family | Test coverage | Real-grid status |
|---|---|---|
| `configure server` / connection | Mocked | Not verified |
| `show grid` / `show views` | Mocked | Not verified |
| `configure zone add/modify/delete` | Mocked | Not verified |
| `show zone` | Mocked | Not verified |
| DNS records (host, A, AAAA, CNAME, MX, TXT, PTR) | Mocked | Not verified |
| `show record` | Mocked | Not verified |
| `configure network add/modify/delete` | Mocked | Not verified |
| `show network` | Mocked | Not verified |
| Network split/join/move | Mocked | Not verified |
| IPAM next_available / next_network | Mocked | Not verified |
| Network containers | Mocked | Not verified |
| Shared networks | Mocked | Not verified |
| Network templates | Mocked | Not verified |
| DHCP ranges and fixed addresses | Mocked | Not verified |
| DHCP MAC filters | Mocked | Not verified |
| DHCP failover associations | Mocked | Not verified |
| Option spaces and option definitions | Mocked | Not verified |
| `show lease` | Mocked | Not verified |
| Admin users/groups/roles | Mocked | Not verified |
| Admin permissions | Mocked | Not verified |
| RADIUS users and devices | Mocked | Not verified |
| Grid members | Mocked | Not verified |
| NS groups / views / shared record groups | Mocked | Not verified |
| `restart dns/dhcp/all` | Mocked | Not verified |
| `restart status` | Mocked | Not verified |
| Scheduled tasks | Mocked | Not verified |
| Extensible attribute definitions | Mocked | Not verified |
| `upload/download csv` | Mocked | Not verified |
| `upload/download leases` | Mocked | Not verified |
| `upload/download cert` | Mocked | Not verified |
| `generate selfsigned cert` | Mocked | Not verified |
| `generate csr` | Mocked | Not verified |
| `show csv task` / `download csv_errors` | Mocked | Not verified |

## What "mocked" means

Each mocked test:

1. Intercepts all HTTP calls via `httpx.MockTransport`.
2. Returns pre-defined JSON responses matching documented WAPI response shapes.
3. Asserts that the correct HTTP method, URL, and body were sent.

This tests the ibcli-side logic thoroughly but does not exercise NIOS behaviour - field validation, access control, referential constraints, or version-specific quirks.

## Getting real-grid access

If you have access to a NIOS lab grid:

1. Install ibcli: `pip install -e python/`
2. Connect: `ibcli -k -s <gridmaster> -u admin`
3. Run commands and compare output to the documentation.
4. Report discrepancies as issues.

Contributions of real-grid test results are welcome.
