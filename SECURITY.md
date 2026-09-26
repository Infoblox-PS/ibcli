# Security policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting on this repository:
[Report a vulnerability](https://github.com/Infoblox-PS/ibcli/security/advisories/new). The report is visible only to
the maintainers until an advisory is published.

Please include:

- the ibcli version (`ibcli --version`) and the `ibx-nios-sdk` version;
- the NIOS version the grid is running, if the issue involves a grid;
- what you did, what happened, and what you expected;
- a proof of concept, if you have one.

Expect an acknowledgement within five working days. Please do not disclose publicly until a fix is available.

**Never include real credentials, WAPI cookies, grid backups or support bundles in a report.** If a reproduction
needs one, say so and it will be arranged privately.

## Supported versions

Fixes land on the latest release. There are no long-term support branches.

| Version | Supported |
|---|---|
| 1.0.x | Yes |
| < 1.0 | No |

## Scope

ibcli is a client. It holds grid credentials in memory for the length of a session, writes a command history to
`~/.ibcli_history` and reads connection settings from `.ibcli.cf`. Reports about credential handling, TLS
verification (including how `-k` relaxes it), history contents and configuration-file handling are in scope.

Vulnerabilities in NIOS itself, or in the WAPI, are not in scope here - report those through Infoblox Support.
