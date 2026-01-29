"""Sphinx configuration for cpitd documentation."""

project = "cpitd"
copyright = "2025, cpitd contributors"
author = "cpitd contributors"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
