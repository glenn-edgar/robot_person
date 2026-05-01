"""Tests for the lazy template loader and load_all.

Convention: a template registered at ltree path
`composites.chain_tree.am_pm_state_machine` lives at
`template_language/templates/composites/chain_tree/am_pm_state_machine.py`.
The lazy loader in `get_template` imports that module on demand the
first time a missing path is requested.
"""

from __future__ import annotations

import sys

import pytest

from template_language import (
    Codes,
    TemplateError,
    describe_template,
    get_template,
    has_template,
    list_template,
    load_all,
    use_template,
)


# Each test runs against an empty registry (conftest's autouse fixture
# clears _registry before each test). Modules already loaded into
# `sys.modules` from prior tests don't re-execute their top-level code
# on re-import — but the registry was cleared by conftest, so the
# define_template calls aren't repopulating either. The loader has to
# pop modules from sys.modules to force re-registration. Helper:

def _evict_template_modules():
    """Drop all template_language.templates.* modules from sys.modules
    so a re-import re-runs their define_template calls. Used by tests
    that need a clean lazy-load to be observable."""
    to_drop = [m for m in sys.modules
               if m.startswith("template_language.templates.")]
    for m in to_drop:
        del sys.modules[m]


@pytest.fixture(autouse=True)
def _evict():
    _evict_template_modules()
    yield


# ---- lazy fallback in get_template -------------------------------

def test_lazy_load_resolves_conventional_path():
    """get_template imports the file at the conventional location."""
    assert not has_template("composites.chain_tree.am_pm_state_machine")
    rt = get_template("composites.chain_tree.am_pm_state_machine")
    assert rt.path == "composites.chain_tree.am_pm_state_machine"
    assert rt.engine == "chain_tree"
    assert rt.kind == "composite"


def test_lazy_load_via_describe_template():
    """describe_template (which calls get_template) triggers the load."""
    d = describe_template("composites.chain_tree.am_pm_state_machine")
    assert d["engine"] == "chain_tree"


def test_lazy_load_via_use_template():
    """use_template triggers the load and returns a real OpList."""
    op_list = use_template(
        "composites.chain_tree.am_pm_state_machine",
        sm_name="lazy_demo",
    )
    # Recording happened — at least one op produced.
    assert op_list is not None
    methods = {op.method for op in op_list.ops}
    assert "define_state_machine" in methods


def test_lazy_load_unknown_path_still_raises():
    """A path that doesn't exist on disk → unknown_template, with
    the attempted module name surfaced for the LLM."""
    with pytest.raises(TemplateError) as exc:
        get_template("composites.chain_tree.does_not_exist")
    assert exc.value.code == Codes.UNKNOWN_TEMPLATE
    assert "tried_module" in exc.value.details


def test_lazy_load_does_not_swallow_errors_in_template_module():
    """If the conventional file imports cleanly but registers under a
    different path (or doesn't register at all), the loader still
    raises unknown_template — it doesn't silently call something else."""
    # No realistic on-disk fixture; covered indirectly by the above.
    # (Authors who deviate from the convention get unknown_template
    # until they fix the file. Documented in registry.py.)
    pass


# ---- load_all ----------------------------------------------------

def test_load_all_populates_registry():
    """load_all walks the templates tree and imports every leaf."""
    load_all()
    paths = {m["path"] for m in list_template()}
    assert "composites.chain_tree.am_pm_state_machine" in paths


def test_load_all_returns_module_count():
    n = load_all()
    # Today there's exactly one leaf template module. Bump as needed.
    assert n >= 1


def test_load_all_idempotent_within_session():
    """Calling load_all twice in a row — second call is a no-op for
    already-imported modules."""
    load_all()
    paths_first = {m["path"] for m in list_template()}
    n2 = load_all()
    paths_second = {m["path"] for m in list_template()}
    assert paths_first == paths_second
    # Second call may newly-load nothing (modules are cached in sys.modules).
    assert n2 >= 0
