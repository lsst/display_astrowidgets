"""Sphinx configuration file for an LSST stack package.

This configuration only affects single-package Sphinx documentation builds.
"""

from documenteer.sphinxconfig.stackconf import build_package_configs
import lsst.display.astrowidgets


_g = globals()
_g.update(build_package_configs(
    project_name='lsst.display.astrowidgets',
    version=lsst.display.astrowidgets.version.__version__))
