# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
# -- Path setup --------------------------------------------------------------
# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

sys.path.insert(0, os.path.abspath("../"))


html_logo = "images/cglogo.png"
html_theme_options = {
    "sidebar_hide_name": True,
    "announcement": "These docs are undergoing active development and may change.",
}

# -- Project information -----------------------------------------------------

project = "changegen"
author = "`Gaia GPS <https://www.gaiagps.com/map>`_ / `Outside Interactive Inc. <https://www.outsideinc.com>`_"


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx_click.ext",
    "sphinxcontrib.apidoc",
]
apidoc_module_dir = "../changegen"
apidoc_output_dir = "source/"
apidoc_separate_modules = True
apidoc_extra_args = ["-E", "-f", "-e"]
# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.

html_theme = "furo"
html_show_copyright = False
html_show_sphinx = False
# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# Autodoc options
autodoc_mock_imports = [
    "tqdm",
    "shapely",
    "gdal",
    "lxml",
    "psycopg2",
    "pyproj",
    "rtree",
    "osmium",
    "osgeo",
    "ogr",
    "numpy",
]
autodoc_member_order = "bysource"