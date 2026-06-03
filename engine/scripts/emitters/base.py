#!/usr/bin/env python3
"""
emitters/base.py — the output-target contract.

An Emitter renders a populated canonical `Collector` into one output format. The
builder builds the model once; each selected emitter renders it. Adding an output
target = one drop-in emitter file (mirrors the source-adapter model).

Contract:
    class MyEmitter(Emitter):
        name = "my-target"
        def emit(self, collector, out_dir, *, subject="person", meta=None): ...

- `subject` ∈ {"person","company"} re-roots the same graph; emitters that don't
  distinguish may ignore it.
- `meta` is a free dict (sources_used, etc.) for report lines.
- Emitters must honor the privacy guarantees already enforced in the Collector —
  they never see raw third-party emails/phones or message bodies, so they can't
  leak them; keep it that way (don't reach around the Collector).
"""


class Emitter:
    """Abstract output-target contract. A subclass sets `name` and implements
    emit(); the builder builds the canonical Collector once and lets each selected
    emitter render it. Emitters must respect the Collector's privacy guarantees —
    don't reach around it to raw third-party PII or message bodies."""

    name = "base"

    def emit(self, collector, out_dir, *, subject="person", meta=None):
        """Render the populated `collector` into `out_dir` for this target.
        `subject` ("person"/"company") re-roots the graph; `meta` is a free dict of
        run info. Subclasses must override (this base raises NotImplementedError)."""
        raise NotImplementedError
