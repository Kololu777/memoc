from importlib.metadata import version


project = "memoc"
author = "Kololu777"
copyright = "2026, Kololu777"
release = version("memory-core")
version = release

language = "ja"
root_doc = "index"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.doctest",
    "sphinx.ext.viewcode",
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autosectionlabel_prefix_document = True

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"
html_title = f"memoc {release} 仕様書"
html_short_title = "memoc"
html_show_sourcelink = False
