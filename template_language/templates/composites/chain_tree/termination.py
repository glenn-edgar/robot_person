"""composites.chain_tree.termination — delayed engine shutdown.

After `delay_seconds`, fires `asm_terminate_system()` which sets
`engine["cfl_engine_flag"] = False` and tears down the target tree.
For typical single-KB chains this stops chain_tree processing of that
KB; in multi-KB chains, it stops all KBs (the whole engine).

Optional log messages bracket the delay so the audit trail shows
intent ("system shutting down in 30s") and execution ("now exiting").

Slots:
  name           required STRING — column name.
  delay_seconds  required FLOAT  — seconds to wait before terminating.
                                    Required (no default) so the user
                                    must declare intent explicitly.
  pre_log        optional STRING=None — message logged before the wait.
                                          None → no log op recorded.
  post_log       optional STRING=None — message logged after the wait,
                                          before terminate. None → no
                                          log op recorded.
  auto_start     optional BOOL=True — passed to define_column.
"""

from __future__ import annotations

from typing import Optional

from template_language import ct, define_template


def termination(*, name: str, delay_seconds: float,
                pre_log: Optional[str] = None,
                post_log: Optional[str] = None,
                auto_start: bool = True):
    """Wait `delay_seconds`, then terminate the engine."""
    ct.define_column(name, auto_start=auto_start)
    if pre_log is not None:
        ct.asm_log_message(pre_log)
    ct.asm_wait_time(delay_seconds)
    if post_log is not None:
        ct.asm_log_message(post_log)
    ct.asm_terminate_system()
    ct.end_column()


define_template(
    path="composites.chain_tree.termination",
    fn=termination,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "shutdown_gate",
        "delay_seconds": 30.0,
        "pre_log": "system shutting down in 30s",
        "post_log": "exiting now",
    },
)
