# Vendored third-party code

tessctl needs a YAML parser. Stock macOS ships `/usr/bin/python3` (3.9) without
PyYAML, and a person installing Tess OS should not have to run `pip`. So
tessctl uses the system PyYAML when it is installed and falls back to this
vendored copy when it is not (see the import block near the top of
`.tess/bin/tessctl`).

| Package | Version | Source | sdist sha256 | Licence |
|---|---|---|---|---|
| PyYAML (pure-Python `lib/yaml`, unmodified) | 6.0.3 | https://pypi.org/project/PyYAML/6.0.3/ | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` | MIT, `yaml/LICENSE` |

The C accelerator (`_yaml`) is not vendored; `yaml/cyaml.py` imports it
optionally and PyYAML falls back to its pure-Python loader and dumper.

To upgrade: download the sdist from PyPI, check its sha256 against the PyPI
JSON API, copy `lib/yaml/` over `yaml/` unmodified, and update this table.
