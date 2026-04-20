"""Oneshot builtins.

o_call signature:  fn(inst, node)              — fires once per activation
io_call signature: fn(inst, node)              — fires once per instance lifetime

Trimmed from the LuaJIT set: log/dict_log/dict_set/dict_inc/queue_event (o_call)
and dict_load (io_call). The hash / stack / external-field / type-split
variants are dropped (spec §What Is Dropped).

Logger destination is pluggable via inst.module["logger"] (default: print).
"""

from __future__ import annotations

from se_runtime.instance import push_event


# ---------------------------------------------------------------------------
# Logging (o_call)
# ---------------------------------------------------------------------------

def log(inst, node) -> None:
    msg = node["params"]["message"]
    inst["module"]["logger"](f"[log] {msg}")


def dict_log(inst, node) -> None:
    """Print a message plus the current value of dictionary[key]."""
    msg = node["params"]["message"]
    key = node["params"]["key"]
    value = inst["module"]["dictionary"].get(key)
    inst["module"]["logger"](f"[dict_log] {msg} {key}={value}")


# ---------------------------------------------------------------------------
# Dictionary writes (o_call)
# ---------------------------------------------------------------------------

def dict_set(inst, node) -> None:
    inst["module"]["dictionary"][node["params"]["key"]] = node["params"]["value"]


def dict_inc(inst, node) -> None:
    """In-place increment. params['delta'] defaults to 1; pass negative to decrement."""
    d = inst["module"]["dictionary"]
    key = node["params"]["key"]
    delta = node["params"].get("delta", 1)
    d[key] = (d.get(key) or 0) + delta


# ---------------------------------------------------------------------------
# Event emission (o_call)
# ---------------------------------------------------------------------------

def queue_event(inst, node) -> None:
    """Push an event onto the engine's event queue.

    params:
        event_id: str
        priority: "high" | "normal"   (default "normal")
        data:     dict                (default {})
    """
    params = node["params"]
    push_event(
        inst,
        event_id=params["event_id"],
        event_data=params.get("data") or {},
        priority=params.get("priority", "normal"),
    )


# ---------------------------------------------------------------------------
# Dictionary init (io_call)
# ---------------------------------------------------------------------------

def dict_load(inst, node) -> None:
    """Merge params['source'] into the module dictionary, once per lifetime.

    Used for startup initialization when a tree needs additional dict entries
    beyond what the DSL emitted. Existing keys are overwritten; constants are
    not touched (constants live in a separate MappingProxyType).
    """
    source = node["params"]["source"]
    inst["module"]["dictionary"].update(source)
