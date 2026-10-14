# matplan

Personal meal planner: high protein, low kcal, high volume, with current grocery prices from stores in Kungälv and Ytterby. Spec: gopnikzxc/Testproject1#1.

## Get started

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/matplan plan                          # show a 3-day block
.venv/bin/matplan installningar                 # list settings
.venv/bin/matplan installningar kcal_mal 1800   # change a setting
.venv/bin/pytest
```

The database is stored at `~/.local/share/matplan/matplan.db`. Set `MATPLAN_DB` to use a different file.

## Status

This is the tracer bullet (#2). Lunch and dinner cover the whole daily target, and the catalog has hand-entered nutrition values and placeholder prices.
