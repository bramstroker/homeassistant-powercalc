# -- Project information

project = "Powercalc"
copyright = "2023, Bram Gerritsen"
author = "Bramstroker"

# -- Options for HTML output

html_theme = "sphinx_rtd_theme"

# -- Options for EPUB output
epub_show_urls = "footnote"

html_static_path = ["_static"]

extensions = ["sphinx_tabs.tabs"]

# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = [
    "css/custom.css",
]

# make rst_epilog a variable, so you can add other epilog parts to it
rst_epilog = ""
# Read link all targets from file
with open("links.rst") as f:
    rst_epilog += f.read()
