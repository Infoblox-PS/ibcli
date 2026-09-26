# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Infoblox Inc.

"""Shared transport helpers for the WAPI fileop protocol.

Fileop transfers are a three-step dance:

1. ``POST /wapi/vX/fileop?_function=<init>`` - returns ``{token, url}``.
2. A raw HTTP transfer against ``url``, which points at Apache's
   ``/http_direct_file_io`` handler, **not** at a WAPI endpoint.
3. ``POST /wapi/vX/fileop?_function=<complete>`` - commits the transfer.

Steps 1 and 3 go through ``client.misc.fileop`` like any other SDK call.
Step 2 has no SDK equivalent, so it is centralised here - together with the
two undocumented NIOS requirements that make it work:

- **Downloads** must send ``Content-Type: application/force-download``.
  Without it Apache answers ``415 Unsupported Media Type``. See
  ``docs/reference/troubleshooting.md``.
- **Uploads** must be a ``multipart/form-data`` POST with a ``file`` part and
  explicit HTTP Basic credentials. The ``http_direct_file_io`` handler does
  not honour the ``ibapauth`` session cookie the SDK relies on, so a
  cookie-only request comes back ``401 Unauthorized``.

Both helpers reach into ``NiosClient._http`` because the SDK exposes no
public hook for non-WAPI transfers. Keeping that access in one module means
there is a single place to update if the SDK grows a public API for it.
"""

from __future__ import annotations

from pathlib import Path

import httpx

# Apache on NIOS rejects the http_direct_file_io GET with 415 unless the
# client declares the media type it expects.
DOWNLOAD_HEADERS = {"Content-Type": "application/force-download"}

_CHUNK = 65536


def _http(client):
    """Return the SDK's internal HttpClient for *client*."""
    return client._http


async def stream_download(client, url: str, dest_path: str | Path) -> None:
    """Stream ``url`` into ``dest_path``, chunked, with the force-download header.

    The body lands in a sibling ``.part`` file that is renamed into place
    only after the last chunk arrives. A transfer that dies halfway would
    otherwise leave a truncated file at *dest_path* that looks exactly like a
    successful download - for a backup or a certificate, that is worse than
    no file at all.

    Args:
        client: A connected ``NiosClient``.
        url: Absolute ``http_direct_file_io`` URL from the fileop init call.
        dest_path: Local path to write the body to.

    Raises:
        httpx.HTTPStatusError: If the transfer returns a non-2xx status.
    """
    transport = _http(client)._client
    dest_path = Path(dest_path)
    part_path = dest_path.with_name(dest_path.name + ".part")
    try:
        async with transport.stream("GET", url, headers=DOWNLOAD_HEADERS) as response:
            response.raise_for_status()
            with open(part_path, "wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size=_CHUNK):
                    fh.write(chunk)
    except BaseException:
        part_path.unlink(missing_ok=True)
        raise
    # os.replace semantics: atomic on the same filesystem, and overwrites an
    # existing destination the way the direct-write version did.
    part_path.replace(dest_path)


async def multipart_upload(client, url: str, source_path: str | Path) -> None:
    """POST ``source_path`` to ``url`` as multipart/form-data with Basic auth.

    A standalone ``httpx.Request`` is built so the SDK client's default
    ``Content-Type: application/json`` header does not clobber the multipart
    boundary httpx derives from ``files=``.

    The file is handed to httpx as an open handle rather than as bytes, so it
    is read in chunks while the body is encoded. Certificates are small, but
    the same endpoint carries database backups and restores, which are not.

    Args:
        client: A connected ``NiosClient``.
        url: Absolute ``http_direct_file_io`` URL from ``uploadinit``.
        source_path: Local file to send.

    Raises:
        httpx.HTTPStatusError: If the transfer returns a non-2xx status.
    """
    http = _http(client)
    source_path = Path(source_path)
    auth = httpx.BasicAuth(http._username, http._password)
    with open(source_path, "rb") as fh:
        files = {"file": (source_path.name, fh, "application/octet-stream")}
        request = httpx.Request("POST", url, files=files)
        response = await http._client.send(request, auth=auth)
    response.raise_for_status()
