"""composites.chain_tree.time_gate — fire body on window entry, then exit.

Variant of `fire_in_window` that adds an explicit `on_exit` slot:
after the wall-clock window closes, the column either RESETs (re-arming
for the next entry) or TERMINATEs (column ends; parent decides what's
next).

Body shape:
    column <name>:
      asm_wait_until_in_time_window(start, end)
      <body splice>
      asm_wait_until_out_of_time_window(start, end)
      asm_reset()       OR  asm_terminate()
    end_column

Slots:
  name        required STRING — column name.
  start       required DICT   — wall-clock window start.
  end         required DICT   — wall-clock window end.
  body        required ACTION — zero-arg callable; splices ops between
                                 the two wait leaves.
  on_exit     required STRING — "reset" | "terminate". Decision is at
                                 template-body time; invalid values raise
                                 ValueError at expansion. Other engine
                                 controls (halt, disable, terminate_system)
                                 are intentionally excluded — column
                                 children are already disabled at exit.
  auto_start  optional BOOL=True — passed to define_column(auto_start=...).
"""

from __future__ import annotations

from typing import Callable

from template_language import ct, define_template


_VALID_ON_EXIT = ("reset", "terminate")


def time_gate(*, name: str, start: dict, end: dict, body: Callable,
              on_exit: str, auto_start: bool = True):
    """Run `body` once on window entry; on exit, reset or terminate."""
    if on_exit not in _VALID_ON_EXIT:
        raise ValueError(
            f"time_gate: on_exit must be one of {_VALID_ON_EXIT}, got {on_exit!r}"
        )

    ct.define_column(name, auto_start=auto_start)
    ct.asm_wait_until_in_time_window(start=start, end=end)
    body()
    ct.asm_wait_until_out_of_time_window(start=start, end=end)
    if on_exit == "reset":
        ct.asm_reset()
    else:  # "terminate"
        ct.asm_terminate()
    ct.end_column()


define_template(
    path="composites.chain_tree.time_gate",
    fn=time_gate,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "biz_hours_gate",
        "start": {"hour": 9},
        "end": {"hour": 17},
        "body": "lambda: ct.asm_log_message('inside hours')",
        "on_exit": "reset",
    },
)
