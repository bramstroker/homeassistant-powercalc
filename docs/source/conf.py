import sys, os

sys.path.append(os.path.abspath('ext'))
sys.path.append('.')

"""
Tells Sphinx which extensions to use.
"""

#extensions = ['xref']

"""
Imports all link files into project.
"""

# from links.link import *
# from links import *

# -- Project information

project = 'Powercalc'
copyright = '2023, Bram Gerritsen'
author = 'Bramstroker'

release = '0.1'
version = '0.1.0'

# -- General configuration

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

# -- Options for HTML output

html_theme = 'sphinx_rtd_theme'

# -- Options for EPUB output
epub_show_urls = 'footnote'

html_static_path = ['_static']

# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = [
    'css/custom.css',
]
