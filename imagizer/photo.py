#!/usr/bin/env python 
# -*- coding: UTF8 -*-
#******************************************************************************\
#* $Source$
#* $Id$
#*
#* Copyright (C) 2006 - 2011,  Jérôme Kieffer <imagizer@terre-adelie.org>
#* Conception : Jérôme KIEFFER, Mickael Profeta & Isabelle Letard
#* Licence GPL v2
#*
#* This program is free software; you can redistribute it and/or modify
#* it under the terms of the GNU General Public License as published by
#* the Free Software Foundation; either version 2 of the License, or
#* (at your option) any later version.
#*
#* This program is distributed in the hope that it will be useful,
#* but WITHOUT ANY WARRANTY; without even the implied warranty of
#* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#* GNU General Public License for more details.
#*
#* You should have received a copy of the GNU General Public License
#* along with this program; if not, write to the Free Software
#* Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#*
#*****************************************************************************/
"""
Module containing most classes for handling images
"""

__author__ = "Jérôme Kieffer"
__date__ = "20110901"
__licence__ = "GPLv2"
__contact__ = "imagizer@terre-adelie.org"


import os, logging, shutil, time
import os.path as op
installdir = op.dirname(__file__)
logger = logging.getLogger("imagizer.photo")

try:
    import Image, ImageStat, ImageChops, ImageFile
except:
    raise ImportError("Selector needs PIL: Python Imaging Library\n PIL is available from http://www.pythonware.com/products/pil/")
try:
    import pygtk ; pygtk.require('2.0')
    import gtk
    import gtk.glade as GTKglade
except ImportError:
    raise ImportError("Selector needs pygtk and glade-2 available from http://www.pygtk.org/")
#Variables globales qui sont des CONSTANTES !
gtkInterpolation = [gtk.gdk.INTERP_NEAREST, gtk.gdk.INTERP_TILES, gtk.gdk.INTERP_BILINEAR, gtk.gdk.INTERP_HYPER]
#gtk.gdk.INTERP_NEAREST    Nearest neighbor sampling; this is the fastest and lowest quality mode. Quality is normally unacceptable when scaling down, but may be OK when scaling up.
#gtk.gdk.INTERP_TILES    This is an accurate simulation of the PostScript image operator without any interpolation enabled. Each pixel is rendered as a tiny parallelogram of solid color, the edges of which are implemented with antialiasing. It resembles nearest neighbor for enlargement, and bilinear for reduction.
#gtk.gdk.INTERP_BILINEAR    Best quality/speed balance; use this mode by default. Bilinear interpolation. For enlargement, it is equivalent to point-sampling the ideal bilinear-interpolated image. For reduction, it is equivalent to laying down small tiles and integrating over the coverage area.
#gtk.gdk.INTERP_HYPER    This is the slowest and highest quality reconstruction function. It is derived from the hyperbolic filters in Wolberg's "Digital Image Warping", and is formally defined as the hyperbolic-filter sampling the ideal hyperbolic-filter interpolated image (the filter is designed to be idempotent for 1:1 pixel mapping).


from config import Config
config = Config()
if config.ImageCache > 1:
    import imagecache
    imageCache = imagecache.ImageCache(maxSize=config.ImageCache)
else:
    imageCache = None

from exif       import Exif
from exiftran   import Exiftran
from fileutils  import mkdir, makedir, smartSize
from encoding   import unicode2ascii


##########################################################
# # # # # # Début de la classe photo # # # # # # # # # # #
##########################################################
class Photo(object):
    """class photo that does all the operations available on photos"""
    _gaussianKernelFFT = None

    def __init__(self, filename):
        self.filename = filename
        self.fn = op.join(config.DefaultRepository, self.filename)
        self.metadata = None
        self.pixelsX = None
        self.pixelsY = None
        self.pil = None
        self.exif = None
        if not op.isfile(self.fn):
            logger.error("No such photo %s" % self.fn)
#        self.bImageCache = (imageCache is not None)
        self.scaledPixbuffer = None
        self.orientation = 1

    def LoadPIL(self):
        """Load the image"""
        self.pil = Image.open(self.fn)

    def larg(self):
        """width-height of a jpeg file"""
        self.taille()
        return self.pixelsX - self.pixelsY

    def taille(self):
        """width and height of a jpeg file"""
        if self.pixelsX == None and self.pixelsY == None:
            self.LoadPIL()
            self.pixelsX, self.pixelsY = self.pil.size

    def SaveThumb(self, strThumbFile, Size=160, Interpolation=1, Quality=75, Progressive=False, Optimize=False, ExifExtraction=False):
        """save a thumbnail of the given name, with the given size and the interpolation methode (quality) 
        resampling filters :
        NONE = 0
        NEAREST = 0
        ANTIALIAS = 1 # 3-lobed lanczos
        LINEAR = BILINEAR = 2
        CUBIC = BICUBIC = 3
        """
        if  op.isfile(strThumbFile):
            logger.warning("Thumbnail %s exists" % strThumbFile)
        else:
            if self.exif is None:
                self.exif = Exif(self.fn)
                self.exif.read()
            extract = False
            print "process file %s exists" % strThumbFile
            if ExifExtraction:
                try:
                    self.exif.dumpThumbnailToFile(strThumbFile[:-4])
                    extract = True
                except (OSError, IOError):
                    extract = False
                #Check if the thumbnail is correctly oriented
                if op.isfile(strThumbFile):
                    thumbImag = Photo(strThumbFile)
                    if self.larg() * thumbImag.larg() < 0:
                        print("Warning: thumbnail was not with the same orientation as original: %s" % self.filename)
                        os.remove(strThumbFile)
                        extract = False
            if not extract:
#                print "on essaie avec PIL"
                if self.pil is None:
                    self.LoadPIL()
                copyOfImage = self.pil.copy()
                copyOfImage.thumbnail((Size, Size), Interpolation)
                copyOfImage.save(strThumbFile, quality=Quality, progressive=Progressive, optimize=Optimize)
            try:
                os.chmod(strThumbFile, config.DefaultFileMode)
            except OSError:
                print("Warning: unable to chmod %s" % strThumbFile)


    def Rotate(self, angle=0):
        """does a looseless rotation of the given jpeg file"""
        if os.name == 'nt' and self.pil != None:
            del self.pil
        self.taille()
        x = self.pixelsX
        y = self.pixelsY
        logger.debug("Before rotation %i, x=%i, y=%i, scaledX=%i, scaledY=%i" % (angle, x, y, self.scaledPixbuffer.get_width(), self.scaledPixbuffer.get_height()))

        if angle == 90:
            if imageCache is not None:
                Exiftran.rotate90(self.fn)
#                os.system('%s -ip -9 "%s" &' % (exiftran, self.fn))
                newPixbuffer = self.scaledPixbuffer.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
                self.pixelsX = y
                self.pixelsY = x
                self.metadata["Resolution"] = "%i x % i" % (y, x)
            else:
                Exiftran.rotate90(self.fn)
#                os.system('%s -ip -9 "%s" ' % (exiftran, self.fn))
                self.pixelsX = None
                self.pixelsY = None
        elif angle == 270:
            if imageCache is not None:
                Exiftran.rotate270(self.fn)
#                os.system('%s -ip -2 "%s" &' % (exiftran, self.fn))
                newPixbuffer = self.scaledPixbuffer.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
                self.pixelsX = y
                self.pixelsY = x
                self.metadata["Resolution"] = "%i x % i" % (y, x)
            else:
                Exiftran.rotate270(self.fn)
#                os.system('%s -ip -2 "%s" ' % (exiftran, self.fn))
                self.pixelsX = None
                self.pixelsY = None
        elif angle == 180:
            if imageCache is not None:
                Exiftran.rotate180(self.fn)
#                os.system('%s -ip -1 "%s" &' % (exiftran, self.fn))
                newPixbuffer = self.scaledPixbuffer.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
            else:
                Exiftran.rotate180(self.fn)
#                os.system('%s -ip -1 "%s" ' % (exiftran, self.fn))
                self.pixelsX = None
                self.pixelsY = None
        else:
            print "Erreur ! il n'est pas possible de faire une rotation de ce type sans perte de donnée."
        if imageCache is not None:
            self.scaledPixbuffer = newPixbuffer
        logger.debug("After   rotation %i, x=%i, y=%i, scaledX=%i, scaledY=%i" % (angle, self.pixelsX, self.pixelsY, self.scaledPixbuffer.get_width(), self.scaledPixbuffer.get_height()))


    def RemoveFromCache(self):
        """remove the curent image from the Cache .... for various reasons"""
        if imageCache is not None:
            if self.filename in imageCache.ordered:
                imageCache.imageDict.pop(self.filename)
                index = imageCache.ordered.index(self.filename)
                imageCache.ordered.pop(index)
                imageCache.size -= 1


    def Trash(self):
        """Send the file to the trash folder"""
        self.RemoveFromCache()
        Trashdir = op.join(config.DefaultRepository, config.TrashDirectory)
        td = op.dirname(op.join(Trashdir, self.filename))
        if not op.isdir(td):
            makedir(td)
        shutil.move(self.fn, op.join(Trashdir, self.filename))


    def readExif(self):
        """
        return exif data + title from the photo
        """
        clef = {'Exif.Image.Make':'Marque',
 'Exif.Image.Model':'Modele',
 'Exif.Photo.DateTimeOriginal':'Heure',
 'Exif.Photo.ExposureTime':'Vitesse',
 'Exif.Photo.FNumber':'Ouverture',
# 'Exif.Photo.DateTimeOriginal':'Heure2',
 'Exif.Photo.ExposureBiasValue':'Bias',
 'Exif.Photo.Flash':'Flash',
 'Exif.Photo.FocalLength':'Focale',
 'Exif.Photo.ISOSpeedRatings':'Iso' ,
# 'Exif.Image.Orientation':'Orientation'
}

        if self.metadata is None:
            self.metadata = {}
            self.metadata["Taille"] = "%.2f %s" % smartSize(op.getsize(self.fn))
            self.exif = Exif(self.fn)
            self.exif.read()
            self.metadata["Titre"] = self.exif.comment
            try:
                rate = self.exif["Exif.Image.Rating"]
            except KeyError:
                self.metadata["Rate"] = 0
                self.exif["Exif.Image.Rating"] = 0
#            except TypeError:
#                logger.warning("%s metadata[Rate] is set to %s, type %s" % (self.filename, self.exif["Exif.Image.Rating"], type(self.exif["Exif.Image.Rating"])))
#                self.metadata["Rate"] = 0
#                self.exif["Exif.Image.Rating"] = 0
            else:
                if isinstance(rate, (int, float, str)): # pyexiv2 v0.1
                    self.metadata["Rate"] = int(float(rate))
                else: # pyexiv2 v0.2+
                    self.metadata["Rate"] = int(rate.value)


            if self.pixelsX and self.pixelsY:
                self.metadata["Resolution"] = "%s x %s " % (self.pixelsX, self.pixelsY)
            else:
                try:
                    self.pixelsX = self.exif["Exif.Photo.PixelXDimension"]
                    self.pixelsY = self.exif["Exif.Photo.PixelYDimension"]
                except (IndexError, KeyError):
                    self.taille()
                self.metadata["Resolution"] = "%s x %s " % (self.pixelsX, self.pixelsY)
            if "Exif.Image.Orientation" in self.exif.exif_keys:
                self.orientation = self.exif["Exif.Image.Orientation"]
            for key in clef:
                try:
                    self.metadata[clef[key]] = self.exif.interpretedExifValue(key).decode(config.Coding).strip()
                except (IndexError, KeyError):
                    self.metadata[clef[key]] = u""
        return self.metadata.copy()


    def has_title(self):
        """
        return true if the image is entitled
        """
        if self.metadata == None:
            self.readExif()
        if  self.metadata["Titre"]:
            return True
        else:
            return False


    def show(self, Xsize=600, Ysize=600):
        """
        return a pixbuf to shows the image in a Gtk window
        """

        scaled_buf = None
        if Xsize > config.ImageWidth :
            config.ImageWidth = Xsize
        if Ysize > config.ImageHeight:
            config.ImageHeight = Ysize
        self.taille()

#        Prepare the big image to be put in cache
        Rbig = min(float(config.ImageWidth) / self.pixelsX, float(config.ImageHeight) / self.pixelsY)
        if Rbig < 1:
            nxBig = int(round(Rbig * self.pixelsX))
            nyBig = int(round(Rbig * self.pixelsY))
        else:
            nxBig = self.pixelsX
            nyBig = self.pixelsY

        R = min(float(Xsize) / self.pixelsX, float(Ysize) / self.pixelsY)
        if R < 1:
            nx = int(round(R * self.pixelsX))
            ny = int(round(R * self.pixelsY))
        else:
            nx = self.pixelsX
            ny = self.pixelsY

        if self.scaledPixbuffer is None:
            pixbuf = gtk.gdk.pixbuf_new_from_file(self.fn)
#            Put in Cache the "BIG" image
            if Rbig < 1:
                self.scaledPixbuffer = pixbuf.scale_simple(nxBig, nyBig, gtkInterpolation[config.Interpolation])
            else :
                self.scaledPixbuffer = pixbuf
            logger.debug("To Cached  %s, size (%i,%i)" % (self.filename, nxBig, nyBig))
        if (self.scaledPixbuffer.get_width() == nx) and (self.scaledPixbuffer.get_height() == ny):
            scaled_buf = self.scaledPixbuffer
            logger.debug("In cache No resize %s" % self.filename)
        else:
            logger.debug("In cache To resize %s" % self.filename)
            scaled_buf = self.scaledPixbuffer.scale_simple(nx, ny, gtkInterpolation[config.Interpolation])
        return scaled_buf


    def name(self, titre, rate=None):
        """write the title of the photo inside the description field, in the JPEG header"""
        if os.name == 'nt' and self.pil != None:
            self.pil = None
        self.metadata["Titre"] = titre
        if rate is not None:
            self.metadata["Rate"] = rate
            self.exif["Exif.Image.Rating"] = int(rate)
        self.exif.comment = titre

        self.exif.write()


    def renameFile(self, newname):
        """
        rename the current instance of photo:
        -Move the file
        -update the cache
        -change the name and other attributes of the instance 
        -change the exif metadata. 
        """
        oldname = self.filename
        newfn = op.join(config.DefaultRepository, newname)
        os.rename(self.fn, newfn)
        self.filename = newname
        self.fn = newfn
        self.exif = newfn
        if self.exif is not None:
            self.exif = Exif(self.fn)
            self.exif.read()
        if (imageCache is not None) and oldname in imageCache:
            imageCache.rename(oldname, newname)


    def storeOriginalName(self, originalName):
        """
        Save the original name of the file into the Exif.Photo.UserComment tag.
        This tag is usually not used, people prefer the JPEG tag for entiteling images.
        
        @param  originalName: name of the file before it was processed by selector
        @type   originalName: python string
        """
        if self.metadata == None:
            self.readExif()
        self.exif["Exif.Photo.UserComment"] = originalName
        self.exif.write()


    def autorotate(self):
        """does autorotate the image according to the EXIF tag"""
        if os.name == 'nt' and self.pil is not None:
            del self.pil

        self.readExif()
        if self.orientation != 1:
            Exiftran.autorotate(self.fn)
#            os.system('%s -aip "%s" &' % (exiftran, self.fn))
            if self.orientation > 4:
                self.pixelsX = self.exif["Exif.Photo.PixelYDimension"]
                self.pixelsY = self.exif["Exif.Photo.PixelXDimension"]
                self.metadata["Resolution"] = "%s x %s " % (self.pixelsX, self.pixelsY)
            self.orientation = 1


    def contrastMask(self, outfile):
        """Ceci est un filtre de debouchage de photographies, aussi appelé masque de contraste, 
        il permet de rattrapper une photo trop contrasté, un contre jour, ...
        Écrit par Jérôme Kieffer, avec l'aide de la liste python@aful, 
        en particulier A. Fayolles et F. Mantegazza avril 2006
        necessite numpy et PIL."""

        try:
            import numpy
#            import scipy.signal as signal
        except:
            logger.error("This filter needs the numpy library available on https://sourceforge.net/projects/numpy/files/")
            return

        t0 = time.time()
        self.LoadPIL()
        dimX, dimY = self.pil.size
        if self._gaussianKernelFFT is None or self._gaussianKernelFFT.shape != (dimY, dimX):
            logger.info("Gaussian (size=%s) and FFT" % config.ContrastMaskGaussianSize)
            size = 2 * numpy.log(2) * config.ContrastMaskGaussianSize ** 2
            gx = numpy.exp(-((numpy.arange(dimX, dtype="float32") - (dimX / 2.0)) / size) ** 2)
            gx2 = numpy.zeros_like(gx)
            gx2[dimX / 2:] = gx[:-dimX / 2]
            gx2[:dimX / 2] = gx[-dimX / 2:]
            gy = numpy.exp(-((numpy.arange(dimY, dtype="float32") - (dimY / 2.0)) / size) ** 2)
            gy2 = numpy.zeros_like(gy)
            gy2[dimY / 2:] = gy[:-dimY / 2]
            gy2[:dimY / 2] = gy[-dimY / 2:]
            g = numpy.outer(gy2, gx2)
            self.__class__._gaussianKernelFFT = numpy.fft.fft2(g / g.sum()).conjugate()
            logger.info("The Gaussian function and FFT took %.3f" % (time.time() - t0))


        ImageFile.MAXBLOCK = dimX * dimY
        img_array = numpy.fromstring(self.pil.tostring(), dtype="UInt8").astype("float32")
        img_array.shape = (dimY, dimX, 3)
        red, green, blue = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]
        #nota: this is faster than desat2=(ar.max(axis=2)+ar.min(axis=2))/2
        desat_array = (numpy.minimum(numpy.minimum(red, green), blue) + numpy.maximum(numpy.maximum(red, green), blue)) / 2.0
        inv_desat = 255. - desat_array
        blured_inv_desat = numpy.fft.ifft2(numpy.fft.fft2(inv_desat) * self._gaussianKernelFFT).real
        bisi = numpy.round(blured_inv_desat).astype("uint8")
        k = Image.fromarray(bisi, "L").convert("RGB")
        S = ImageChops.screen(self.pil, k)
        M = ImageChops.multiply(self.pil, k)
        F = ImageChops.add(ImageChops.multiply(self.pil, S), ImageChops.multiply(ImageChops.invert(self.pil), M))
        F.save(op.join(config.DefaultRepository, outfile), quality=80, progressive=True, Optimize=True)
        try:
            os.chmod(op.join(config.DefaultRepository, outfile), config.DefaultFileMode)
        except IOError:
            logger.error("Unable to chmod %s" % outfile)
        logger.info("The whoole contrast mask took %.3f" % (time.time() - t0))


########################################################        
# # # # # # fin de la classe photo # # # # # # # # # # #
########################################################

class Signature(object):
    def __init__(self, filename):
        """
        this filter allows add a signature to an image
        """
        self.img = None
        self.sig = Image.open(filename)
        self.sig.convert("RGB")
        (self.xs, self.ys) = self.sig.size
        self.bigsig = self.sig
        #The signature file is entented to be white on a black background, this inverts the color if necessary
        if ImageStat.Stat(self.sig)._getmean() > 127:
            self.sig = ImageChops.invert(self.sig)

        self.orientation = -1 #this is an impossible value
        (self.x, self.y) = (self.xs, self.ys)

    def mask(self, orientation=5):
        """
        x and y are the size of the initial image
        the orientation correspond to the position on a clock :
        0 for the center
        1 or 2 upper right
        3 centered in heith right side ...."""
        if orientation == self.orientation and (self.x, self.y) == self.bigsig.size:
            #no need to change the mask
            return
        self.orientation = orientation
        self.bigsig = Image.new("RGB", (self.x, self.y), (0, 0, 0))
        if self.x < self.xs or self.y < self.ys :
            #the signature is larger than the image
            return
        if self.orientation == 0:
            self.bigsig.paste(self.sig, (self.x / 2 - self.xs / 2, self.y / 2 - self.ys / 2, self.x / 2 - self.xs / 2 + self.xs, self.y / 2 - self.ys / 2 + self.ys))
        elif self.orientation in [1, 2]:
            self.bigsig.paste(self.sig, (self.x - self.xs, 0, self.x, self.ys))
        elif self.orientation == 3:
            self.bigsig.paste(self.sig, (self.x - self.xs, self.y / 2 - self.ys / 2, self.x, self.y / 2 - self.ys / 2 + self.ys))
        elif self.orientation in [ 5, 4]:
            self.bigsig.paste(self.sig, (self.x - self.xs, self.y - self.ys, self.x, self.y))
        elif self.orientation == 6:
            self.bigsig.paste(self.sig, (self.x / 2 - self.xs / 2, self.y - self.ys, self.x / 2 - self.xs / 2 + self.xs, self.y))
        elif self.orientation in [7, 8]:
            self.bigsig.paste(self.sig, (0, self.y - self.ys, self.xs, self.y))
        elif self.orientation == 9:
            self.bigsig.paste(self.sig, (0, self.y / 2 - self.ys / 2, self.xs, self.y / 2 - self.ys / 2 + self.ys))
        elif self.orientation in [10, 11]:
            self.bigsig.paste(self.sig, (0, 0, self.xs, self.ys))
        elif self.orientation == 12:
            self.bigsig.paste(self.sig, (self.x / 2 - self.xs / 2, 0, self.x / 2 - self.xs / 2 + self.xs, self.ys))
        return

    def substract(self, inimage, orientation=5):
        """apply a substraction mask on the image"""
        self.img = inimage
        self.x, self.y = self.img.size
        ImageFile.MAXBLOCK = self.x * self.y
        self.mask(orientation)
        k = ImageChops.difference(self.img, self.bigsig)
        return k


class RawImage:
    """ class for handling raw images
    - extract thumbnails
    - copy them in the repository
    """
    def __init__(self, strRawFile):
        """
        Contructor of the class
        
        @param strRawFile: path to the RawImage 
        @type strRawFile: string
        """
        self.strRawFile = strRawFile
        self.exif = None
        self.strJepgFile = None
        logger.info("Importing [Raw|Jpeg] image %s" % strRawFile)

    def getJpegPath(self):

        if self.exif is None:
            self.exif = Exif(self.strRawFile)
            self.exif.read()
        if self.strJepgFile is None:
            self.strJepgFile = unicode2ascii("%s-%s.jpg" % (
                    self.exif.interpretedExifValue("Exif.Photo.DateTimeOriginal").replace(" ", os.sep).replace(":", "-", 2).replace(":", "h", 1).replace(":", "m", 1),
                    self.exif.interpretedExifValue("Exif.Image.Model").strip().split(",")[-1].replace("/", "").replace(" ", "_")
                    ))
            while op.isfile(op.join(config.DefaultRepository, self.strJepgFile)):
                number = ""
                idx = None
                listChar = list(self.strJepgFile[:-4])
                listChar.reverse()
                for val in listChar:
                    if val.isdigit():
                        number = val + number
                    elif val == "-":
                        idx = int(number)
                        break
                    else:
                        break
                if idx is None:
                    self.strJepgFile = self.strJepgFile[:-4] + "-1.jpg"
                else:
                    self.strJepgFile = self.strJepgFile[:-5 - len(number)] + "-%i.jpg" % (idx + 1)
        dirname = op.dirname(op.join(config.DefaultRepository, self.strJepgFile))
        if not op.isdir(dirname):
            makedir(dirname)

        return self.strJepgFile

    def extractJPEG(self):
        """
        extract the raw image to its right place
        """
        extension = op.splitext(self.strRawFile)[1].lower()
        strJpegFullPath = op.join(config.DefaultRepository, self.getJpegPath())
        if extension in config.RawExtensions:
            data = os.popen("%s %s" % (config.Dcraw, self.strRawFile)).readlines()
            img = Image.fromstring("RGB", tuple([int(i) for i in data[1].split()]), "".join(tuple(data[3:])))
            img.save(strJpegFullPath, format='JPEG')
            #Copy all metadata useful for us.
            exifJpeg = Exif(strJpegFullPath)
            exifJpeg.read()
            exifJpeg['Exif.Image.Orientation'] = 1
            exifJpeg["Exif.Photo.UserComment"] = self.strRawFile
            for metadata in [ 'Exif.Image.Make', 'Exif.Image.Model', 'Exif.Photo.DateTimeOriginal', 'Exif.Photo.ExposureTime', 'Exif.Photo.FNumber', 'Exif.Photo.ExposureBiasValue', 'Exif.Photo.Flash', 'Exif.Photo.FocalLength', 'Exif.Photo.ISOSpeedRatings']:
                try:
                    exifJpeg[metadata] = self.exif[metadata]
                except:
                    logger.error("Unable to copying metadata %s in file %s, value: %s" % (metadata, self.strRawFile, self.exif[metadata]))
            #self.exif.copyMetadataTo(self.strJepgFile)

            exifJpeg.writeMetadata()

        else: #in config.Extensions, i.e. a JPEG file
            shutil.copy(self.strRawFile, strJpegFullPath)
            Exiftran.autorotate(strJpegFullPath)

        os.chmod(strJpegFullPath, config.DefaultFileMode)