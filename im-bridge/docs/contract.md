# AuRevior evaluation contract

The bridge accepts an exact chat name or confirmed conversation ID and a half-open time interval in ISO 8601 with explicit UTC offsets. Every returned row is verified against the resolved chat and the requested period.

The output envelope remains `ok/data` or `ok/error`. Message content can be readable, unavailable, or unsupported. Stable references supplied by the previous adapter are not reusable across backends. AuRevior references are deterministic hashes of the chat, upstream local ID, timestamp, sender, type and text.

Reads request up to 10,001 rows at once and return at most 10,000, avoiding offset shifts while an account is active. Results identify upstream read failures and the result limit. The query API cannot prove complete coverage across database shards, so the bridge reports partial coverage.

The packaged runtime probes configured Windows x64 Python 3.14. The only supported live data operations are exact-contact resolution and conversation history. The installation does not consume settings from any previous Skill.
