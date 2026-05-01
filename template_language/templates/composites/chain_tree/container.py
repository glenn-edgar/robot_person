"""composites.chain_tree.container — column wrapping a list of children.

Each child in `children` is a zero-arg callable whose `ct.*` ops splice
into this column. Children typically call `use_template(...)` for nested
composites or emit leaf `ct.asm_*` ops directly.

The column behavior is sequential (children run in declared order; each
HALTs while busy and DISABLEs when done) — see ct_builtins/column.py.

Slots:
  name        required STRING — column name.
  children    required LIST   — list of zero-arg Callables.
  auto_start  optional BOOL=True — passed to define_column.
"""

from __future__ import annotations

from template_language import ct, define_template


def container(*, name: str, children: list, auto_start: bool = True):
    """Open a column, splice each child in declared order, close."""
    ct.define_column(name, auto_start=auto_start)
    for child in children:
        child()
    ct.end_column()


define_template(
    path="composites.chain_tree.container",
    fn=container,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "startup_sequence",
        "children": "[lambda: ct.asm_log_message('starting'), "
                    "lambda: ct.asm_terminate_system()]",
    },
)
