import unittest

import lsst.utils.tests
try:
    import lsst.display.astrowidgets as displayAstrowidgets
except ImportError:
    displayAstrowidgets = None
    pass


class ImportTest(unittest.TestCase):
    def testImport(self):
        if displayAstrowidgets is not None:
            self.assertTrue(hasattr(displayAstrowidgets, "AstroWidgetsVersion"))


class TestMemory(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
