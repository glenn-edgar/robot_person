"""coffee_maker — worked example of the three-layer template model.

Demonstrates a project that lives outside the template_language
package and registers itself as a templates root with prefix
`project.coffee_maker`. After `bootstrap()` runs, lazy-loading any
path under that prefix resolves to the corresponding file inside
`coffee_maker.templates`.

Layout:
  templates/
    leaves/chain_tree/brew_log.py            project leaf (reused)
    solutions/chain_tree/morning_kb.py       project solution composing
                                             system + project + inline

See `bootstrap.py` for registration; `run.py` for a runnable entry point.
"""
