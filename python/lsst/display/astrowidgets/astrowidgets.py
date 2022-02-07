# This file is part of display_ds9.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["Ds9Error", "DisplayImpl"]

import sys
from astropy.table import Table

import lsst.afw.display.interface as interface
import lsst.afw.display.virtualDevice as virtualDevice
import lsst.afw.display.ds9Regions as ds9Regions
import lsst.afw.geom as afwGeom

from ginga.misc.log import get_logger
from ginga.AstroImage import AstroImage
from ginga.util.wcsmod.wcs_astropy import AstropyWCS

import astrowidgets


class Ds9Error(IOError):
    """Represents an error communicating with Astrowidgets
    """


try:
    _maskTransparency
except NameError:
    _maskTransparency = None


def AstroWidgetsVersion():
    """Get the version of DS9 in use.

    Returns
    -------
    version : `str`
        Version of DS9 in use.
    """
    return astrowidgets.__version__


class AstroWidgetsEvent(interface.Event):
    """An event generated by a mouse or key click on the display"""

    def __int__(self, k, x, y):
        interface.Event.__init__(self, k, x, y)


class DisplayImpl(virtualDevice.DisplayImpl):
    """Virtual device display implementation.
    """
    markerDict = {'+': 'plus', 'x': 'cross', '.': 'circle', '*': 'circle', 'o': 'circle'}

    def __init__(self, display, dims=None, use_opencv=False, verbose=False, *args, **kwargs):
        virtualDevice.DisplayImpl.__init__(self, display, verbose)
        if dims is None:
            width, height = 1024, 768
        else:
            width, height = dims
        self.logger = get_logger("ginga", log_stderr=True, level=40)
        self._viewer = astrowidgets.ImageWidget(image_width=width, image_height=height,
                                                use_opencv=use_opencv, logger=self.logger)
        self._defaultMarkTagName = 'all'
        self._callbackDict = dict()

        self._gingaViewer = self._viewer._viewer  # We want to display the IW, but ginga has all the handles

        bd = self._gingaViewer.get_bindings()
        bd.enable_all(True)
        self._canvas = self._viewer.canvas
        self._canvas.enable_draw(False)
        self._maskTransparency = 0.8
        self._redraw = True

    def embed(self):
        """Attach this display to the output of the current cell."""
        return self._viewer  # .embed()

    def get_viewer(self):
        """Return the ginga viewer"""
        return self._viewer

    def show_color_bar(self, show=True):
        """Show (or hide) the colour bar"""
        self._gingaViewer.show_color_bar(show)

    def show_pan_mark(self, show=True, color='red'):
        """Show (or hide) the colour bar"""
        self._gingaViewer.show_pan_mark(show, color)

    def _setMaskTransparency(self, transparency, maskplane):
        """Specify mask transparency (percent); or None to not set it when loading masks"""
        if maskplane is not None:
            print("display_astrowidgets is not yet able to set transparency for individual maskplanes" % maskplane,  # noqa E501
                  file=sys.stderr)
            return

        self._maskTransparency = 0.01*transparency

    def _getMaskTransparency(self, maskplane=None):
        """Return the current mask transparency"""
        return self._maskTransparency

    def _mtv(self, image, mask=None, wcs=None, title=""):
        """Display an Image and/or Mask on a ginga display"""
        self._erase()
        self._canvas.delete_all_objects()

        Aimage = AstroImage(inherit_primary_header=True)
        Aimage.set_data(image.getArray())

        if "mask_overlay" in self._gingaViewer.canvas.get_tags():
            self._gingaViewer.canvas.delete_object_by_tag("mask_overlay")

        self._gingaViewer.set_image(Aimage)

        if wcs is not None:
            _wcs = AstropyWCS(self.logger)
            Aimage.lsst_wcs = WcsAdaptorForGinga(wcs)
            _wcs.pixtoradec = Aimage.lsst_wcs.pixtoradec
            _wcs.pixtosystem = Aimage.lsst_wcs.pixtosystem
            _wcs.radectopix = Aimage.lsst_wcs.radectopix

            Aimage.set_wcs(_wcs)
            Aimage.wcs.wcs = Aimage.lsst_wcs

        if mask:
            maskColorFromName = {'BAD': 'red',
                                 'SAT': 'green',
                                 'INTRP': 'green',
                                 'CR': 'magenta',
                                 'EDGE': 'yellow',
                                 'DETECTED': 'blue',
                                 'DETECTED_NEGATIVE': 'cyan',
                                 'SUSPECT': 'yellow',
                                 'NO_DATA': 'orange',
                                 'CROSSTALK': None,
                                 'UNMASKEDNAN': None}
            maskDict = dict()
            for plane, bit in mask.getMaskPlaneDict().items():
                color = maskColorFromName.get(plane, None)
                if color:
                    maskDict[1 << bit] = color
            # CZW: This value of 0.9 is pretty thick for the alpha.
            self.overlay_mask(mask, maskDict,
                              self._maskTransparency)
        self._flush()

    def overlay_mask(self, maskImage, maskDict, maskAlpha):
        import numpy as np
        from ginga.RGBImage import RGBImage
        from ginga import colors

        maskArray = maskImage.getArray()
        height, width = maskArray.shape
        maskRGBA = np.zeros((height, width, 4), dtype=np.uint8)
        nSet = np.zeros_like(maskArray, dtype=np.uint8)

        for maskValue, maskColor in maskDict.items():
            r, g, b = colors.lookup_color(maskColor)
            isSet = (maskArray & maskValue) != 0
            if (isSet == 0).all():
                continue

            maskRGBA[:, :, 0][isSet] = 255 * r
            maskRGBA[:, :, 1][isSet] = 255 * g
            maskRGBA[:, :, 2][isSet] = 255 * b

            nSet[isSet] += 1

        maskRGBA[:, :, 3][nSet == 0] = 0
        maskRGBA[:, :, 3][nSet != 0] = 255 * (1 - maskAlpha)

        nSet[nSet == 0] = 1
        for C in (0, 1, 2):
            maskRGBA[:, :, C] //= nSet

        rgb_img = RGBImage(data_np=maskRGBA)
        Image = self._viewer.canvas.get_draw_class('image')
        maskImageRGBA = Image(0, 0, rgb_img)

        if "mask_overlay" in self._gingaViewer.canvas.get_tags():
            self._gingaViewer.canvas.delete_object_by_tag("mask_overlay")
        self._gingaViewer.canvas.add(maskImageRGBA, tag="mask_overlay")

    def _buffer(self, enable=True):
        self._redraw = not enable

    def _flush(self):
        self._gingaViewer.redraw(whence=3)

    def _erase(self):
        """Erase the display"""
        self._canvas.delete_all_objects()
        self._viewer.reset_markers()

    def _dot(self, symb, c, r, size, ctype, fontFamily="helvetica", textAngle=None, label='_dot'):
        """Draw a symbol at (col,row) = (c,r) [0-based coordinates]
        Possible values are:
            +                Draw a +
            x                Draw an x
            *                Draw a *
            o                Draw a circle
            @:Mxx,Mxy,Myy    Draw an ellipse with moments (Mxx, Mxy, Myy) (argument size is ignored)
            An object derived from afwGeom.ellipses.BaseCore Draw the ellipse (argument size is ignored)
            Any other value is interpreted as a string to be drawn. Strings
            obey the fontFamily (which may be extended with other
            characteristics, e.g. "times bold italic".  Text will be drawn
            rotated by textAngle (textAngle is ignored otherwise).
        N.b. objects derived from BaseCore include Axes and Quadrupole.
        """
        dataTable = Table([{'x': c, 'y': r}])
        if symb in '+x*.o':
            self._viewer.marker = {'type': self.markerDict[symb], 'color': ctype, 'radius': size}
            self._viewer.add_markers(dataTable, marker_name=label)
            self._flush()
        # if isinstance(symb, afwGeom.ellipses.BaseCore):
        #     Ellipse = self._canvas.get_draw_class('ellipse')

        #     self._canvas.add(Ellipse(c, r, xradius=symb.getA(), yradius=symb.getB(),
        #                              rot_deg=math.degrees(symb.getTheta()), color=ctype),
        #                      redraw=self._redraw)
        else:
            Line = self._canvas.get_draw_class('line')
            Text = self._canvas.get_draw_class('text')

            for ds9Cmd in ds9Regions.dot(symb, c, r, size, fontFamily="helvetica", textAngle=None):
                tmp = ds9Cmd.split('#')
                cmd = tmp.pop(0).split()
                comment = tmp.pop(0) if tmp else ""

                cmd, args = cmd[0], cmd[1:]
                if cmd == "line":
                    self._gingaViewer.canvas.add(Line(*[float(p) - 1 for p in args], color=ctype),
                                                 redraw=self._redraw)
                elif cmd == "text":
                    x, y = [float(p) - 1 for p in args[0:2]]
                    self._gingaViewer.canvas.add(Text(x, y, symb, color=ctype), redraw=self._redraw)
                else:
                    raise RuntimeError(ds9Cmd)
                if comment:
                    print(comment)  # CZW

    def _drawLines(self, points, ctype):
        """Connect the points, a list of (col,row)
        Ctype is the name of a colour (e.g. 'red')
        """
        Line = self._gingaViewer.canvas.get_draw_class('line')
        p0 = points[0]
        for p in points[1:]:
            self._gingaViewer.canvas.add(Line(p0[0], p0[1], p[0], p[1], color=ctype), redraw=self._redraw)
            p0 = p

    def beginMarking(self, symb='+', ctype='cyan', size=10, label='interactive'):
        self._viewer.start_marking(marker_name=label,
                                   marker={'type': self.markerDict[symb], 'color': ctype, 'radius': size})

    def endMarking(self):
        self._viewer.stop_marking()

    def getMarkers(self, label='interactive'):
        # This could do marker labels better.
        return self._viewer.get_markers(marker_name=label)

    def clearMarkers(self, label=None):
        if label:
            self._viewer.remove_markers(label)
        else:
            self._viewer.reset_markers()

    def linkMarkers(self, ctype='brown', label='interactive'):
        # I don't have a good way to clear these.
        Line = self._gingaViewer.canvas.get_draw_class('line')
        table = self._viewer.get_markers(marker_name=label)

        x0, y0 = (0, 0)
        for rowCount, (x, y) in enumerate(table.iterrows('x', 'y')):
            if rowCount != 0:
                self._gingaViewer.canvas.add(Line(x0, y0, x, y, color=ctype), redraw=self._redraw)
            x0 = x
            y0 = y

    #
    # Set gray scale
    #
    def _scale(self, algorithm, min, max, unit, *args, **kwargs):
        self._gingaViewer.set_color_map('gray')
        self._gingaViewer.set_color_algorithm(algorithm)

        if min == "zscale":
            self._gingaViewer.set_autocut_params('zscale', contrast=0.25)
            self._gingaViewer.auto_levels()
        elif min == "minmax":
            self._gingaViewer.set_autocut_params('minmax')
            self._gingaViewer.auto_levels()
        else:
            if unit:
                print("ginga: ignoring scale unit %s" % unit, file=sys.stderr)

            self._gingaViewer.cut_levels(min, max)

    def _show(self):
        """Show the requested display
        In this case, embed it in the notebook (equivalent to Display.get_viewer().show();
        see also Display.get_viewer().embed()
        N.b.  These command *must* be the last entry in their cell
        """
        return self._gingaViewer.show()

    #
    # Zoom and Pan
    #
    def _zoom(self, zoomfac):
        """Zoom by specified amount"""
        self._gingaViewer.scale_to(zoomfac, zoomfac)

    def _pan(self, colc, rowc):
        """Pan to (colc, rowc)"""
        self._gingaViewer.set_pan(colc, rowc)

    def _getEvent(self):
        """Listen for a key press on a frame in DS9 and return an event.

        Returns
        -------
        event : `Ds9Event`
            Event with (key, x, y).
        """
        pass


# Copy ginga's WCS implementation
class WcsAdaptorForGinga(AstropyWCS):
    """A class to adapt the LSST Wcs class for Ginga.

    This was taken largely from the afw.display.ginga package.
    """
    def __init__(self, wcs):
        self._wcs = wcs

    def pixtoradec(self, idxs, coords='data'):
        """Return (ra, dec) in degrees given a position in pixels"""
        ra, dec = self._wcs.pixelToSky(*idxs)

        return ra.asDegrees(), dec.asDegrees()

    def pixtosystem(self, idxs, system=None, coords='data'):
        """I'm not sure if ginga really needs this; equivalent to self.pixtoradec()"""
        return self.pixtoradec(idxs, coords=coords)

    def radectopix(self, ra_deg, dec_deg, coords='data', naxispath=None):
        """Return (x, y) in pixels given (ra, dec) in degrees"""
        return self._wcs.skyToPixel(ra_deg*afwGeom.degrees, dec_deg*afwGeom.degrees)

    def all_pix2world(self, *args, **kwargs):
        out = []
        print(f"{args}")
        for pos in args[0]:
            r, d = self.pixtoradec(pos)
            out.append([r, d])
            return tuple(out)

    def datapt_to_wcspt(self, *args):
        return (0.0, 0.0)

    def wcspt_to_datapt(self, *args):
        return (0.0, 0.0)
