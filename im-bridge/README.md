# IM-into-Agent for AuRevior

Windows x64 evaluation Skill. The Skill requires an installed Windows x64 Python 3.14 and uses an offline copy of the public AuRevior 0.6.1 reader.

- `setup.ps1 -CheckOnly` verifies the packaged Python imports and CLI.
- The user prepares a local AuRevior configuration independently. Run `setup.ps1 -ConfigPath <path to config.json>` to validate and select it once. Only the selected path is saved.
- `setup.ps1` rechecks the selected configuration. `config_validated` verifies the required files and source directory. An authorized read is needed to verify database connectivity.
- `bridge.ps1 read --chat <name> --since <time> --until <time>` accepts a half-open interval with explicit offsets.

Queries use a single bounded history request to avoid offset shifts between calls. Results remain partial because the upstream interface provides no reliable shard coverage signal. An individual message is marked unread when its underlying media is unavailable. This implementation does not transcribe audio.

AuRevior decrypts the database shards touched by a read into a temporary directory. The bridge removes that directory at the end of each ordinary call. Abrupt process termination can leave it behind. This evaluation should be run with synthetic data unless the user expressly allows temporary whole-shard plaintext.

See [contract](docs/contract.md).
