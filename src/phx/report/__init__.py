"""``phx report``: resource trends and fixed-rule recommendations (Phase 12f, ADR-0032).

Read-only over the ``run.jsonl`` files PHX already keeps; it calls no model and never
writes under the state root or in a repo. A default run saves a vault note and charts
(ADR-0035). ``load`` reads the logs, ``model`` aggregates them, ``rules``
turns the aggregates into recommendations, ``render`` and ``svg`` print them.
"""
