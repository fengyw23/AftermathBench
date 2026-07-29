# Forgejo native release-prefix evidence

This directory archives the sanitized outputs of GitHub Actions run
`30429795403` (`forgejo-source-audit`, conclusion `success`) at commit
`f2830462ea0074c1734b9391ee54cd821a8ce023`.

The run:

- built Forgejo from pinned source revision
  `fbafae6c6288f3448aa6932576841f5daf5a9c76`;
- restored the native SQLite/repository snapshot deterministically;
- created the release task prefix using 15 successful public Forgejo writes;
- signed in through Forgejo's normal web interface and read the native webhook
  delivery history;
- confirmed that the pre-failure history was empty.

The archived files intentionally exclude runtime credentials, snapshots and
container logs. SHA-256 values:

| File | SHA-256 |
|---|---|
| `forgejo-source-verification.json` | `f71d92b1b3a07152383129595228c1f174fec574329dbd06e3f1a6b9c274bfbb` |
| `release-prefix.json` | `35e1be251c8367d267bcbb069214314225c814f425bbdb08c7e7a0f75a336f0d` |
| `restored.json` | `ffe54882b6290d467e43722a15fc3f93c566e9a61cddf00da2f1410610807fb6` |
| `webhook-history.json` | `978fa668720342f49aa32a81b898a4cb349fb6cfaa895828fafada45a3ee4286` |

This evidence validates only source provenance, reset and prefix construction.
Matched fault boundaries and recovery correctness are validated by later runs.
