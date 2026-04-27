"""ct_bridge — s_engine-side bridge functions for the CFL↔SE boundary.

The single export users care about is `BRIDGE_FN_REGISTRY`: a dict of
{name: callable} merged into every s_engine module's `fn_registry` by
SE_MODULE_LOAD_INIT. Lets serialized s_engine trees reference bridge fns
by string name; in-memory trees can also import the callables directly
from `ct_bridge.fns`.
"""

from __future__ import annotations

from .fns import BRIDGE_FN_REGISTRY

__all__ = ["BRIDGE_FN_REGISTRY"]
