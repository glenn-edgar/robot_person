"""Multi-root registry tests.

Covers `register_template_root(package, prefix)` per continue.md
§"Multi-root namespacing":

  - Default root (empty prefix) is pre-registered for
    `template_language.templates`; existing system paths still resolve.
  - A second root registered with a non-empty prefix routes
    namespaced lazy-imports to that root's package.
  - Most-specific (longest) prefix wins when prefixes nest.
  - Duplicate prefix → ValueError (per the no-silent-overwrite rule).
  - Cross-root duplicate full path → DUPLICATE_PATH at registration.
  - `load_all` walks every registered root.
"""

from __future__ import annotations

import sys

import pytest

from template_language import (
    Codes,
    TemplateError,
    describe_template,
    get_template,
    list_template,
    list_template_roots,
    load_all,
    register_template_root,
    use_template,
)


# Drop the fixture root's modules between tests so define_template
# re-runs after the registry is cleared by conftest.

def _evict_fixture_modules():
    to_drop = [m for m in sys.modules
               if m.startswith("template_language.tests._fixture_root.")
               or m.startswith("template_language.templates.")]
    for m in to_drop:
        del sys.modules[m]


@pytest.fixture(autouse=True)
def _evict():
    _evict_fixture_modules()
    yield


# ---- default root regression -------------------------------------

def test_default_root_present():
    roots = list_template_roots()
    assert any(r["prefix"] == "" and r["package"] == "template_language.templates"
               for r in roots), roots


def test_default_root_resolves_system_template():
    """Existing system templates keep working under the default root."""
    rt = get_template("composites.chain_tree.am_pm_state_machine")
    assert rt.engine == "chain_tree"


# ---- non-default root --------------------------------------------

FIXTURE_PKG = "template_language.tests._fixture_root"
FIXTURE_PREFIX = "project.fixture"
FIXTURE_PATH = f"{FIXTURE_PREFIX}.leaves.chain_tree.probe"


def test_register_root_appears_in_list():
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    prefixes = {r["prefix"] for r in list_template_roots()}
    assert FIXTURE_PREFIX in prefixes


def test_lazy_load_via_prefixed_root():
    """A path under the fixture prefix maps to the fixture package's
    module tree and the lazy loader imports + registers it."""
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    rt = get_template(FIXTURE_PATH)
    assert rt.path == FIXTURE_PATH
    assert rt.kind == "leaf"
    assert rt.engine == "chain_tree"


def test_use_template_via_prefixed_root_records_ops():
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    op_list = use_template(FIXTURE_PATH)
    assert op_list is not None
    methods = {op.method for op in op_list.ops}
    assert "asm_log_message" in methods


def test_describe_template_via_prefixed_root():
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    d = describe_template(FIXTURE_PATH)
    assert d["path"] == FIXTURE_PATH
    assert d["engine"] == "chain_tree"


# ---- prefix-resolution semantics ---------------------------------

def test_longest_prefix_wins():
    """When multiple prefixes could match, the most-specific (longest)
    one is consulted first."""
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    # Add a more general project root that shouldn't claim the path.
    register_template_root("nonexistent.package", prefix="project")
    rt = get_template(FIXTURE_PATH)
    # Resolved through the longer prefix, NOT the shorter "project" root.
    assert rt.path == FIXTURE_PATH


def test_unmatched_prefix_falls_to_default_root():
    """A path not under any non-default prefix falls through to the
    empty-prefix default root."""
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    # The default root resolves system templates regardless of the
    # extra root being registered.
    rt = get_template("leaves.chain_tree.print_hello")
    assert rt.path == "leaves.chain_tree.print_hello"


# ---- error paths -------------------------------------------------

def test_duplicate_prefix_raises():
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    with pytest.raises(ValueError, match="already registered"):
        register_template_root("other.package", prefix=FIXTURE_PREFIX)


def test_duplicate_default_prefix_raises():
    """The empty-prefix root is pre-registered; re-registering it
    should hard-error rather than silently shadow."""
    with pytest.raises(ValueError, match="already registered"):
        register_template_root("other.package", prefix="")


def test_invalid_prefix_raises():
    with pytest.raises(ValueError, match="dot-separated identifiers"):
        register_template_root("pkg", prefix="bad/prefix")
    with pytest.raises(ValueError, match="dot-separated identifiers"):
        register_template_root("pkg", prefix="trailing.")


def test_unknown_path_under_registered_prefix_raises_template_error():
    """A path under a registered prefix whose file is missing → the
    standard UNKNOWN_TEMPLATE error, with the attempted module name
    surfaced for the LLM."""
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    with pytest.raises(TemplateError) as exc:
        get_template(f"{FIXTURE_PREFIX}.leaves.chain_tree.does_not_exist")
    assert exc.value.code == Codes.UNKNOWN_TEMPLATE
    assert exc.value.details["tried_module"].endswith(
        "._fixture_root.leaves.chain_tree.does_not_exist"
    )


# ---- load_all walks every root -----------------------------------

def test_load_all_walks_registered_roots():
    register_template_root(FIXTURE_PKG, prefix=FIXTURE_PREFIX)
    load_all()
    paths = {m["path"] for m in list_template()}
    assert FIXTURE_PATH in paths
    # Default root still loaded too.
    assert "composites.chain_tree.am_pm_state_machine" in paths
