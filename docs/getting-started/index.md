# Getting Started

This section walks you from zero to running your first ibcli commands against an Infoblox NIOS grid.

## Prerequisites

- **Python 3.11 or later** - check with `python --version`.
- **Network access** to a NIOS grid master on HTTPS (port 443).
- The `ibcli` source tree (this repository).

## Steps

1. [Install ibcli](installation.md) - one `pip install -e .` (or `poetry install`) command.
2. [First connection](first-connection.md) - connect to your grid and run a command.
3. [Tab completion](tab-completion.md) - learn the tab-driven UX that makes ibcli productive.

## Five-minute preview

```bash
# Install
pip install -e .                        # or: poetry install

# Connect and run a one-shot command
ibcli -s gridmaster.corp.example -u admin -p s3cr3t -k \
           -e "show zone example.com"

# Interactive REPL
ibcli -s gridmaster.corp.example -u admin -k
Password: ****
admin@gridmaster.corp.example > show z<TAB>
  zone
admin@gridmaster.corp.example > show zone ex<TAB>
  example.com
admin@gridmaster.corp.example > show zone example.com
fqdn=example.com view=default
```

Abbreviations work throughout: `co z a example.com` is the same as `configure zone add example.com`.
