# Troubleshooting

## HTTP 415 on file downloads

**Symptom:** `download database` or other download commands fail with:

```
  Error: 415 Unsupported Media Type
```

or the error body contains HTML with a 415 title.

**Cause:** The NIOS `http_direct_file_io` endpoint requires the client to send `Content-Type:
application/force-download` on the GET request in step 2 of the fileop protocol. Without this header, Apache on NIOS
returns a 415 error.

**Status:** Fixed. The header is sent by `stream_download` in `src/ibcli/fileop.py`, which every download command
routes through:

```python
DOWNLOAD_HEADERS = {"Content-Type": "application/force-download"}

async with transport.stream("GET", url, headers=DOWNLOAD_HEADERS) as response:
    ...
```

!!! warning "This regressed once"
    The header lived in a pre-SDK `session.py` that was removed during the port to `ibx-nios-sdk`, and the fix went
    with it - the only test covering it was real-grid-only, so CI stayed green.
    `tests/test_commands_fileops.py::test_download_sends_force_download_content_type` now asserts the header against
    the mock transport.

If you ever see this error recur, verify that the `Content-Type: application/force-download` header is present on the
GET request. Run with `-d 2` to inspect the full HTTP exchange:

```bash
ibcli -k -s gridmaster -u admin -d 2
```

Look for the line beginning `GET http://<gm>/http_direct_file_io/...` and confirm the request headers include
`Content-Type: application/force-download`.

If you are running a version predating commit `bdc4dc1`, upgrade - the header was added in that commit.

---

## Appendix: the fileop 415 debugging saga

This section records how the 415 was diagnosed and fixed, for future reference.

**Initial symptom (commit `2cf4c43` era):** `download database mike.bak` against the real NIOS grid at `192.0.2.40`
(WAPI v2.14) returned:

```
Error: 415 Unsupported Media Type
```

The error came from step 2 of the fileop protocol - the `GET` to `http_direct_file_io`. Steps 1 (`POST
fileop?_function=getgriddata`) and 3 (`POST fileop?_function=downloadcomplete`) succeeded.

**Investigation:** Running with `-d 2` showed the GET request was being sent without a `Content-Type` header. The NIOS
Apache configuration serving `http_direct_file_io` requires the client to declare the media type it is requesting as
`application/force-download`. Without it, Apache returns 415.

This is not documented in the NIOS WAPI Guide. It was discovered by inspecting the NIOS UI's JavaScript source, which
sets this header explicitly when initiating file downloads.

**Fix (commit `bdc4dc1`):** Added `Content-Type: application/force-download` to the download GET. That code lived in
`session.py`, which the `ibx-nios-sdk` port later deleted; the header now lives in `stream_download` in
`src/ibcli/fileop.py`.

**Confirmation:** After the fix, `download database mike.bak` against `192.0.2.40` completed successfully, producing
a valid database backup file.

**Broader implication:** Other `http_direct_file_io` operations (log file downloads, lease history, support bundles,
certificate downloads) have the same undocumented requirement. All route through `stream_download` in
`src/ibcli/fileop.py` and therefore receive the header automatically. Uploads have a matching quirk of their own -
that endpoint ignores the session cookie and needs HTTP Basic auth on the multipart POST; see `multipart_upload` in
the same module. See [Real Grid Status](real-grid-status.md) for the current verified-commands table.

---

## "Not connected" on every command

**Symptom:** Every command prints `  Not connected`.

**Cause:** `configure server` was not called, or failed silently.

**Fix:**

1. Check that you connected successfully: the prompt should change to `user@host >`.
2. Run `configure server <host> user <u> password <p>` explicitly.
3. Check for a `.ibcli.cf` file in your CWD that may be supplying bad credentials.
4. Run with `-d 2` to see the WAPI HTTP exchange.

---

## TLS certificate errors

**Symptom:**

```
  Error: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

**Cause:** The NIOS appliance uses a self-signed certificate (default configuration).

**Fix:** Use `-k` / `--insecure`:

```bash
ibcli -k -s gridmaster.corp.example -u admin
```

To permanently suppress this for a project, add `configure server ... -k` to `.ibcli.cf` or use the flag in every
invocation.

---

## WAPI version errors

**Symptom:**

```
  Error: [404] The requested URL was not found
```

on commands that call WAPI endpoints.

**Cause:** The auto-detected WAPI version may differ from what the grid actually supports, or the version required for
a specific object type is higher than the detected version.

**Fix:** Use `--wapi-version` to pin a version:

```bash
ibcli --wapi-version 2.12 -s gm -u admin
```

Run `show server version` to see the detected version.

---

## Parse errors on valid-looking commands

**Symptom:**

```
   ^--- Unknown argument at marker
```

on a command that looks correct.

**Common causes:**

1. **Abbreviation ambiguity:** Two commands share the same prefix. Add more characters.
2. **`key=value` on the wrong side:** The tokenizer splits `key=value` before parsing. If a value contains `=`, quote
it: `comment="k=v"`.
3. **Set-chain exceeded:** More than 4 `set key=value` pairs - see [Known Quirks](../development/known-quirks.md).

---

## History not persisting

**Symptom:** `~/.ibcli_history` is empty or history is lost between sessions.

**Cause:** If ibcli exits via `Ctrl-C` rather than `Ctrl-D` or `quit`, `prompt_toolkit` may not flush the history file.

**Fix:** Exit cleanly with `quit`, `exit`, `bye`, or `Ctrl-D`.

---

## "Partial state" error after join

**Symptom:**

```
  PARTIAL STATE: 10.0.0.0/24 was already deleted.
  Recover manually: re-create 10.0.0.0/24 or complete deletion of 10.0.1.0/24
```

**Cause:** `configure network join` is not atomic - it deletes both networks then creates the parent. If the second
DELETE fails, one network has been deleted but the parent was not created.

**Fix:** Follow the printed recovery instructions: either re-create the deleted sibling or manually delete the second
network and create the parent.

---

## Timeout on large grids

**Symptom:** `show network` or `show zone` hangs or times out.

**Cause:** The paginated `get_paginated` methods use a 30-second request timeout per page. Large grids with thousands
of objects may need multiple pages.

**Fix:** Use a specific filter to narrow results:

```
show network 10.0.0.0/24
show zone corp.example
```

The WAPI timeout comes from the SDK: `NiosClient(timeout=...)`, 30s by
default. `configure server` does not expose it, so raising it means
editing the `NiosClient(...)` call in `src/ibcli/commands/server.py`.
