Synthetic fixtures shaped like the real output of optional SOCMINT tools.
No real person is represented; usernames/emails/numbers are invented
(`example.invalid`, 555-01xx). Formats follow:

- `maigret_simple_report.json` — Maigret `--json simple` (`maigret/report.py::generate_json_report`; only CLAIMED sites are written)
- `sherlock_print_all.csv` — Sherlock `--csv --print-all` (`sherlock_project/sherlock.py` CSV writer)
- `holehe_results.csv` — holehe `--csv` export (`holehe/core.py::export_csv`, module `out` dict keys)
- `phoneinfoga_local.json` — `phoneinfoga serve` `POST /api/v2/scanners/local/run` response
