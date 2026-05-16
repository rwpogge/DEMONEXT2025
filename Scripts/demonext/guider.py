"""DEMONEXT Guider interface class

Class to implement a variant on the Villanueva science guiding
mode for the DEMONEXT reboot.

Author
------
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2025 Jan 22

Modification History
--------------------
    2025 Jan 22 - first version based on test notebooks [rwp/osu]
    2025 Jan 23 - bug fixes and enhancements from first "live" test [rwp/osu]
    2025 Jan 25 - added guideOffset() method and other tools [rwp/osu]
    2025 Jan 27 - added skySig to imExamine() and where used [rwp/osu]
    
ToDo List
---------
   Flesh out remaining methods, clean up properties, test, test, test
   
"""

import os
import math

# pathlib for path handling

from pathlib import Path

# yaml for configuration file parsing

import yaml

# sep for object detection (python implementation of Source Extractor)

import sep

# numpy for image arrays and analysis

import numpy as np

# use kd-trees for fast star catalog matching from scipy spatial

from scipy import spatial

# astropy for FITS file handling and coordinates

from astropy.io import fits
from astropy.coordinates import SkyCoord
import astropy.units as u

# logging

import logging
logger = logging.getLogger("Guider") 


# Guider Class

class Guider:
    """Science Guider class
    
    Implements a variant on the original DEMONEXT science-image guiding mode
        
    Methods
    -------
    __init__(cfgFile)
        initialize the Guider class instance
       
        cfgFile: string
            full name of the YAML runtime configuration file to load.
            default: looks in $HOME for `.demonext/config/demonext.txt`
    
    Attributes
    ----------

    """
    
    def __init__(self,*args):
        """
        Constructor for the Guider class. 

        Parameters
        ----------
        *args :
            cfgFile : string
                YAML configuration file (including path) that includes focuser setup
            
        Raises
        ------
        RuntimeError
            Raised if the configuration file is not found or cannot be opened.

        Returns
        -------
        None.
        
        Description
        -----------
        The constructor initializes all data structures and properties
        needed to implement science guiding mode.

        If no runtime configuration file is given, it defaults to a file 
        named demonext.txt in the user .demonext/config/ directory 
        (default expectation).  We load it directly rather than using
        the Config class.

        """
        
        # DEMONEXT camera class instance for image acquisition

        self.cam = None

        # Argument options from nothing, a config file, or individual keywords
        
        if len(args) > 0:
            cfgFile = args[0]

        else:  # default config file
            cfgFile = str(Path.home() / ".demonext/config/demonext.txt")

        # open the configuration file and get the info we need
        
        if os.path.exists(cfgFile):
            with open(cfgFile,"r") as stream:
                try:
                    config = yaml.safe_load(stream)
                except yaml.YAMLError as exp:
                    msg = f"Cannot open runtime configuration file {cfgFile}: {exp}"
                    logger.exception(msg)
                    raise RuntimeError(msg)

            # science guider configuration info
                
            try:
                self.sgConfig = config["sciguider"]
            except:
                self.sgConfig = None

            # Telescope and instrument configuration info
            
            try:
                self.instConfig = config["instrument"]
            except:
                self.instConfig = None

            # The directories entry should have the the top-level
            # raw data directory path as "DataDir", otherwise
            # assume the current working directory is "safe"

            try:
                tmpDir = config["directories"]["DataDir"]
                if len(Path(tmpDir).root) == 0: # rootless, assume relative to home
                    self.dataDir = str(Path.home() / tmpDir)
                else:
                    self.dataDir = tmpDir
                    
            except:
                self.dataDir = str(Path.cwd())

        else:
            msg = f"Runtime configuration file {cfgFile} does not exist"
            logger.exception(msg)
            raise RuntimeError(msg)

        # Defaults if no science guider config information. These are based 
        # on experiments with image detection with first-gen DEMONEXT images.

        self.threshold = 10.0 # object detection threshold in background level sigma
        self.minFWHM = 1.25   # minimum object FWHM in pixels (CRE and bad pixel rejection)
        self.maxFWHM = 4.0    # nominal maximum object FHWM in pixels (extended source rejection)
        self.maxEll = 0.3     # maximum image ellipticity (extended object and CRE rejection)
        self.minPeak = 5000.  # minimum peak pixel in adu (faint object rejection)
        self.maxPeak =55000.  # maximum peak pixel in adu (saturated star rejection)
        self.shiftTol = 5.0   # pixel shift tolerance relative to median distance between "matches"
        self.calXStep = 10.0  # guider calibration X step size (seconds)
        self.calYStep = 10.0  # guider calibration Y step size (seconds)
        self.gain = 0.8       # guide-correction gain factor, typically < 1
        self.minStars = 5     # minimum number of stars needed to compute inter-image offsets
        self.ccdRot = 90.0    # approximate rotation between CCD and celestial

        # science guider parameters
        
        self.guide_a = 0.0           # guider NS scale in units of sec/pixel
        self.guide_b = 0.0           # guider EW scale in units of sec/pixel
        self.guide_b0 = 0.0          # guider EW scale at declination 0 degrees
        self.guide_th = -self.ccdRot # guider rotation angle in degrees
        self.filter = 0              # guider calibration filter
        self.calibrated = False      # start out assuming guider uncalibrated

        # reference image parameters

        self.refImg = None      # name of the guiding reference image
        self.refCosDec = 1.0    # cosine of declination of refImg
        self.refX = []          # reference star X pixel coordinates
        self.refY = []          # reference star Y pixel coordinates
        
        # Telescope and instrument defaults if no instrument config in the
        # runtime config file - these are for a PlaneWave CDK20 f/6.8 and
        # an e3v CCD detector with 15-micron pixels
        
        self.telFL = 3454.0  # telesope focal length in mm
        self.pixSize = 0.015 # science CCD pixel size mm
        
        # Update from the runtime config file as needed
        
        if self.sgConfig:
            if "Threshold" in self.sgConfig:
                self.threshold = self.sgConfig["Threshold"]
            if "MinFWHM" in self.sgConfig:
                self.minFWHM = self.sgConfig['MinFWHM']
            if "MaxFWHM" in self.sgConfig:
                self.maxFWHM = self.sgConfig["MaxFWHM"]
            if "MaxEll" in self.sgConfig:
                self.maxEll = self.sgConfig["MaxEll"]
            if "MaxPeak" in self.sgConfig:
                self.maxPeak = self.sgConfig["MaxPeak"]
            if "MinPeak" in self.sgConfig:
                self.minPeak = self.sgConfig["MinPeak"]
            if "OffsetTol" in self.sgConfig:
                self.offsetTol = self.sgConfig["OffsetTol"]
            if "CalXStep" in self.sgConfig:
                self.calXStep = self.sgConfig["CalXStep"]
            if "CalYStep" in self.sgConfig:
                self.calYStep = self.sgConfig["CalYStep"]
            if "Gain" in self.sgConfig:
                self.gain = self.sgConfig["Gain"]
            if "MinStars" in self.sgConfig:
                self.minStars = self.sgConfig["MinStars"]
            if "CCDRotAng" in self.sgConfig:
                self.ccdRot = self.sgConfig["CCDRotAng"]
            if "Guide_A" in self.sgConfig:
                self.guide_a = self.sgConfig["Guide_A"]
            if "Guide_B" in self.sgConfig:
                self.guide_b0 = self.sgConfig["Guide_B"]
            if "Guide_Theta" in self.sgConfig:
                self.guide_th = self.sgConfig["Guide_Theta"]
            
        # telescope and instrument info we need for guiding
        
        if self.instConfig:
            if "FOCALLEN" in self.instConfig:
                self.telFL = self.instConfig["FOCALLEN"]
            if "PIXSIZE" in self.instConfig:
                self.pixSize = self.instConfig["PIXSIZE"]
            
        # pixel scale in arcsec/pixel
        
        self.pixScale = 206265*self.pixSize/self.telFL # arcsec/pixel
        
        # time delays for various operations

        self.timeDelay = 1 # seconds
        self.queryCadence = 0.1 # seconds - fastest we should emit queries to the focuser

        # Useful boolean translation dictionaries

        self.OnOff = {True:"On",False:"Off"}
        self.YesNo = {True:"Yes",False:"No"}

        # operation timeouts

        self.guiderCalTimeout = 120.0   # seconds
                
        # internal messages and verbosity

        self.msg = ""
        self.verbose = False

    # Methods

    #--------------------------------
    #
    # Image measurement methods
    #
    
    def imExamine(self,imgFile,thresh=None):
        """
        Examine an image with sep, return info on objects and sky

        Parameters
        ----------
        imgFile : string
            Full name of a FITS image taken with the science cameras.
        thresh : float, optional
            Detection threshold in sigma above sky. The default is `threshold`.

        Returns
        -------
        numObj : int
            number of objects detected.
        medFWHM : float
            median FWHM of objects detected.
        medEll : float
            median ellipticity of objects detected.
        sky : float
            global estimate of the background sky level in ADU
        skysig : float
            global estimate of the RMS sky noise in ADU
    
        Description
        -----------
        Uses Source Extractor to find objects (stars, galaxies, etc.) on the 
        image brighter than the nominal detection threshold to see if we
        have any objects to work with.
        
        If no threshold given among the arguments, uses the default threshold
        for the current Guide class instance (`threshold`)
        
        See Also
        --------
        findStars
        """
        hdu = fits.open(imgFile,uint=False)
        data = hdu[0].data
        hdu.close()
        
        logger.info(f"Getting image parameters for {imgFile}")
        
        # estimate image background and subtract it
        
        bkg = sep.Background(data)
        
        imgData = data - bkg
        sky = bkg.globalback
        skySig = bkg.globalrms
        
        # find stars and other objects in the image
        
        if not thresh:
            thresh = self.threshold
            
        objects = sep.extract(imgData,thresh,err=skySig)
        
        # how many objects did we detect?
        
        numObj = len(objects)
        
        if numObj == 0:
            self.msg = f"No objects found in {imgFile} at {thresh:.1f}-sigma above sky"
            if self.verbose: print(self.msg)
            logger.error(self.msg)
            return 0,0.0,0.0,bkg.globalback
        else:
            self.msg = f"Found {numObj} objects in {imgFile} at {thresh:.1f}-sigma above sky"
            logger.info(self.msg)
            if self.verbose: print(self.msg)
        
        # we have objects, compute median FWHM and ellipticity
        
        a = np.array(objects['a'])
        b = np.array(objects['b'])
        
        fwhm = np.sqrt(1.5*math.log(2)*(a*a + b*b))
        medFWHM = np.median(fwhm)
        
        ell = 1.0 - (b/a)
        medEll = np.median(ell)
        
        self.msg = f"Image median FWHM={medFWHM:.2f}pix, Ell={medEll:.3f}, sky={sky:.1f} ADU"
        logger.info(self.msg)
        if self.verbose: print(self.msg)
        
        return numObj,medFWHM,medEll,sky,skySig
        
    
    def findStars(self,imgFile,thresh=None):
        """
        Find reference stars good for measuring inter-image shifts on an image

        Parameters
        ----------
        imgFile : float
            Name of a FITS-format image to search for reference stars.

        Returns
        -------
        x : float list
            X pixel coordinates of reference star centroids.
        y: float list
            Y pixel coordinates of reference star centroids.

        Description
        -----------
        Find reference stars on an image using Source Extractor and the
        default search parameters.
        
        A "good" reference star is one that meets these criteria:
         * minFWHM < FWHM < maxFWMM (images are stars)
         * minPeak < peak < maxPeak (peak pixel not too faint or near saturation)
         * ell < maxEll (objects not elongated)
         
        Returns the XY pixel coordinates of stars found, or empty arrays
        if no stars are found.
        
        """
        
        # open the FITS file
    
        hdu = fits.open(imgFile,uint=False)
        data = hdu[0].data
        hdu.close()
    
        logger.info(f"Searching for guide stars in {imgFile}...")
        
        # estimate the sky background and subtract it from the image
    
        bkg = sep.Background(data)

        imgData = data - bkg

        # find stars and other objects in the sky-subtracted image
    
        if not thresh:
            thresh = self.threshold
            
        objects = sep.extract(imgData,thresh,err=bkg.globalrms)
    
        # did we detect any objects?
    
        numObjects = len(objects)
        
        if numObjects < self.minStars:
            self.msg = f"Too few guide stars found: {numObjects} objects < {self.minStars} in {imgFile}"
            logger.error(self.msg)
            if self.verbose: print(self.msg)
            return [],[]
        
        # global average sky level
        
        sky = bkg.globalback
        
        # we have objects, filter on thresholds of FWHM and peak counts
 
        x = np.array(objects['x'])
        y = np.array(objects['y'])
        a = np.array(objects['a'])
        b = np.array(objects['b'])
        peak = np.array(objects['peak'])

        # FWHM and ellipticity
    
        fwhm = np.sqrt(1.5*math.log(2)*(a*a + b*b))
        ell = 1.0 - (b/a)

        # "good star" criteria:
        #   minFWHM < fwhm < maxFWHM - is it compact and a star but bigger than a hot pixel or cre?
        # peak < maxPk = maxPeak-sky (avoids using saturated stars if sky is brighter than Sat-Peak ADU)
        #   ell < ellMax - images are mostly round
    
        maxPk = self.maxPeak - sky 
        self.msg = f"Good guide stars = {self.minFWHM:.1f}<FWHM<{self.maxFWHM:.1f}, ell<{self.maxEll:.3f}, {self.minPeak:.1f} < peak < {maxPk:.1f} ADU"
        logger.info(self.msg)
        if self.verbose: print(self.msg)
        
        goodStar = np.where((fwhm>=self.minFWHM) & (fwhm<=self.maxFWHM) & (ell<=self.maxEll) & (peak >=self.minPeak) & (peak<=maxPk))[0]

        numGood = len(goodStar)
        
        if numGood > self.minStars:
            self.msg = f"Found {numGood} good guide stars on {imgFile}"
            if self.verbose: print(self.msg)
            logger.info(self.msg)
            return x[goodStar],y[goodStar]
        else:
            self.msg = f"Too few good guide stars found: {numGood} < {self.minStars} in {imgFile}"
            if self.verbose: print(self.msg)
            logger.error(self.msg)
            return [],[]
      

    def getCoords(self,imgFile):
        """
        Get image RA,Dec coords from the FITS header

        Parameters
        ----------
        imgFile : string
            Name of a FITS image taken with the science camera.

        Returns
        -------
        coord : astropy.coordinates SkyCoord object
            Image RA/Dec coordnates

        Description
        -----------
        Reads the image FITS header and extracts OBJCTRA and OBJCTDEC which
        are telescope RA/Dec for the image, returns an astropy.coordinates
        `SkyCoords()` object with the coordinates.
        
        """
        hdr = fits.getheader(imgFile)
        ra = hdr['OBJCTRA']
        dec = hdr['OBJCTDEC']
        coord = SkyCoord(ra=ra,dec=dec,unit=(u.hour,u.deg),frame='icrs')        
        return coord
        

    def imgOffset(self,refCoords,targCoords,rot=None):
        """
        Compute offset between two sets of RA/Dec coordinates

        Parameters
        ----------
        refCoords : astropy.coordinates SkyCoords() object
            reference image RA/Dec coordinates
        targCoords : astropy.coordinates SkyCoords() object
            target image RA/Dec coordinates
        rot : float, optional
            Image rotational orientation in degrees.  Default
            is None, uses the default `ccdRot` angle in 
            degrees from the runtime configuration file, or 0.0
            if no entry in the config file.
            
        Returns
        -------
        dx : float
            offset in the CCD X-axis direction in pixels
        dy : float
            offset in the CCD Y-axis direction in pixels
            
        Description
        -----------
        Uses the astropy.coordinates.SkyCoords `spherical_offsets_to()`
        method to compute the offset between two RA/Dec coordinates
        and translate them to CCD XY offset in pixels.
        
        Offset is computed in the (xi,eta) tangent plane to the celestial
        sphere since we expect offsets to be small.
        
        Alignment need only be approximate here (e.g., -90.0 even if 
        -89.123 is more precise).
        
        """

        # RA/Dec offset on the tangent plane
    
        dra, ddec = targCoords.spherical_offsets_to(refCoords)

        xiPix = dra.to(u.arcsec).value/self.pixScale   # pixels in xi (RA)
        etaPix = ddec.to(u.arcsec).value/self.pixScale # pixels in eta (DEC)
    
        # pixel offset
    
        if not rot:
            theta = np.radians(self.ccdRot)
        else:
            theta = np.radians(rot)

        # rotate xi,eta in pixels to CCD dx,dy
        
        dx = xiPix*np.cos(theta) - etaPix*np.sin(theta)
        dy = xiPix*np.sin(theta) + etaPix*np.cos(theta)
        
        return dx, dy


    def findShift(self,refX,refY,targX,targY,dx0=0,dy0=0,tol=5.0):
        """
        Find the median pixel shift between a reference and target star catalogs

        Parameters
        ----------
        refX : float list
            X-axis centroids of stars on the reference image in pixels.
        refY : float list
            Y-axis centroids of stars on the reference image in pixels.
        targX : float list
            X-axis centroids of stars on the target image in pixels.
        targY : float list
            Y-axis centroids of stars on the target image in pixels.
        dx0 : float, optional
            estimated X-axis pixel offset of refXY to targXY. The default is 0 (no shift).
        dy0 : float, optional
            estimated Y-axis pixel offset of refXY to targXY. The default is 0 (no shift).
        tol : float, optional
            distance tolerance in pixels for the kd-tree matcher. The default is 5 pixels.

        Returns
        -------
        dX : float
            median X-axis shift of target image relative to reference image.
        dY : float
            median Y-axis shift of target image relative to reference image.
        dXoff : float list
            X-axis shifts of all the stars matched in both catalogs.
        dYoff : float list
            Y-axis shifts of all the stars matched in both catalogs.
        numMatch : int
            number of matches found between the refernece and target star catalogs.
            
        Description
        -----------
        Uses a kd-tree algorithm to match the XY coordinates of the reference image
        star catalog to the XY coordinatds of stars in the target image.  Because shifts
        can be large but we have a strong prior from reading the RA/Dec coordinates of
        the two images, we can do a rough match of the catalogs before handing them to
        the kd-tree which is an advantage in crowded fields
        
        We define "good" stars as all being within `tol` of the median distance found
        between matches by the kd-tree algorithm.  We use the list of match indexes
        to compute star-by-star offsets in pixels, and the median of the ensemble.

        See Also
        --------
        imgOffset to compute an estimated offset from ra/dec header coords
        
        """
        
        distTol = tol # pixels from median distance
    
        # match the target and reference catalog XY using cKDTree

        targXY = np.dstack([targX,targY])[0]
        refXY = np.dstack([refX+dx0,refY+dy0])[0]

        dist,index = spatial.cKDTree(targXY).query(refXY)

        # cull the match list of mismatches using a common distance range
        # defined as the median distances +/- distTol
    
        medDist = np.median(dist)
        minDist = medDist - distTol
        maxDist = medDist + distTol

        iGood = np.where((dist >= minDist) & (dist <= maxDist))[0]

        # compute shift to get back to the reference XY coordinates
        
        numMatch = len(iGood)
        
        if numMatch == 0:
            self.msg = "Found no matches"
            if self.verbose: print(self.msg)
            logger.error(self.msg)
            return 0,0,[],[],0
        else:
            self.msg = f"Found {numMatch} guide star matches, computing offset..."
            if self.verbose: print(self.msg)
            logger.info(self.msg)
            
        dXoff = targX[index[iGood]] - refX[iGood]
        dYoff = targY[index[iGood]] - refY[iGood]

        # compute median shift in X and Y
    
        dX = np.median(dXoff)
        dY = np.median(dYoff)
        
        self.msg = f"Offset dX={dX:.3f} pix, dY={dY:.3f} pix"
        logger.info(self.msg)
        if self.verbose: print(self.msg)
        
        # return
    
        return dX,dY,dXoff,dYoff,numMatch        
             

    #----------------------------------------
    #
    # Guider calibration
    #
    
    def calibrate(self):
        
        # Take a reference image and measure it, get declination
        # compute cos(dec)
        
        
        # Offset (+mx,0), take calibration image 1, measure offset from ref
        
        
        # Offset (-mx,0), take calibration image 2, measure offset from cal 1
        
        
        # Offset (0,+my), take calibration image 3, measure offset from cal 2
        
        
        # Offset (0,-my), take calibration image 4, measure offset from cal 3
        
        
        # compute guider calibration coefficients a, b, theta

        
        return False
    

    def saveCalibration(self,calFile=None):
        
        # save the guide calibration coefficients in a restart file
        # in guideDir
        
        return False
    
    
    def loadCalibration(self,calFile=None):

        # load a YAML-format science guider calibration file.  If no
        # explicit name is given, see if there is an active calibration
        # file in guideDir

        return False           


    def setCalibration(self,a,b0,theta):
        """
        Set an ad-hoc guider calibration

        Parameters
        ----------
        a : float
            NS guide correction coefficient in sec/pixel.
        b0 : float
            Equatorial EW guide correction coefficient in sec/pixel.
        theta : float
            Guider orientation angle in degrees.

        Returns
        -------
        None.

        Description
        -----------
        Used to define an ad-hoc guider calibration by hand.  Assumes
        you have reasonable values to work with.
        
        Note
        ----
        This is a low-level engineering command and not for routine use.
        
        """
        
        self.guide_a = a
        self.guide_b0 = b0
        self.guide_th = theta
        self.calibrated = True


    def clearCalibration(self):
        """
        Clear the science guider calibration, restoring the runtime state.

        Returns
        -------
        None.

        Description
        -----------
        Executes the relevant parts of the Guider class initialization and
        returns the science guide calibration information in the Class
        to the initial runtime values.
        
        """
        # runtime default science guider parameters
        
        self.guide_a = 0.0           # guider NS scale in units of sec/pixel
        self.guide_b = 0.0           # guider EW scale in units of sec/pixel
        self.guide_b0 = 0.0          # guider EW scale at declination 0 degrees
        self.guide_th = -self.ccdRot # guider rotation angle in degrees
        self.filter = 0              # guider calibration filter
        self.calibrated = False      # start out assuming guider uncalibrated
        
        # if we have  science-guider data from the runtime config file, 
        # restore it here
        
        if self.sgConfig:
            if "Guide_A" in self.sgConfig:
                self.guide_a = self.sgConfig["Guide_A"]
            if "Guide_B" in self.sgConfig:
                self.guide_b0 = self.sgConfig["Guide_B"]
            if "Guide_Theta" in self.sgConfig:
                self.guide_th = self.sgConfig["Guide_Theta"]        
        
        
    #----------------------------------------
    #
    # Science guiding
    #
    
    def guideOffset(self,dX,dY):
        """
        Compute the guider moves in guider XY coordinates that will 
        correct observed star image pixel shift dX, dY

        Parameters
        ----------
        dX : float
            X pixel offset of the target image from the reference image
        dY : float
            Y pixel offset of the target image from the reference image

        Raises
        ------
        RuntimeError
            If there is no active science guider calibration.

        Returns
        -------
        mx : float
            Guider correction offset in guider X
        my : float
            Guider correction offset in guider Y

        Description
        -----------
        Given a pixel shift between a target image and the reference image,
        returns the guider correction that would move the target image stars
        back to the reference image locations.
        
        If no science guider calibration is available, raise exception
        """
        if self.calibrated:
            sinth = np.sin(np.radians(self.guide_th))
            costh = np.cos(np.radians(self.guide_th))
            field_b = self.guide_b0/self.refCosDec
            
            mx = field_b*dY*sinth + self.guide_a*dX*costh
            
            my = field_b*dY*costh - self.guide_a*dX*sinth

            self.msg = f"Pixel offset dX={dX:.3f}, dY={dY:.3f} gives correction mx={mx:.3f}, my={my:.3f}"
            if self.verbose: print(self.msg)
            logger.info(self.msg)
            
            return mx, my

        else:
            self.msg = "Science Guider has no active calibration, cannot compute guide correction"
            if self.verbose: print(self.msg)
            logger.error(self.msg)
            raise RuntimeError(self.msg)
            

    def guiderReset(self):
        """
        Reset field-specific science guider parameters

        Returns
        -------
        None.

        Description
        -----------
        Resets all field-specific science guiding parameters to the original
        runtime defaults and clears the XY reference coordinate arrays.
        
        """
        
        self.refCosDec = 1.0 # reset to safe equatorial value
        self.guide_b = self.guide_b0
        self.refX = []
        self.refY = []
        self.refImg = None
        
        
    def guiderInit(self,refImg):
        """
        Initialize science guiding mode

        Parameters
        ----------
        refImg : string
            Name of the reference image, usually the first science image
            in the sequence to be acquired.

        Raises
        ------
        ValueError
            if the reference image does not exist.
        RuntimeError
            if there are any problems setting up science guiding.

        Returns
        -------
        None.

        Description
        -----------
        Initializes science guiding for a new field, measures the
        positions of guide stars on the reference image, and gets
        info it needs to start science guiding with the next science
        image to be acquired.
        
        """
        # We cannot start science guiding mode if we don't have
        # an active guider calibration
        
        if not self.calibrated:
            self.msg = "No active science guider calibration, cannot initialize science guiding mode"
            if self.verbose: print(self.msg)
            logger.error(self.msg)
            raise RuntimeError(self.msg)
            
        # Open and read in guide reference image
                
        if Path(refImg).exists():
            self.refImg = refImg
        else:
            self.msg = f"Reference image {refImg} not found"
            if self.verbose: print(self.msg)
            logger.error(self.msg)
            raise ValueError(self.msg)
        
        # get image coords with getCoords(), compute cos(dec)
        
        try:
            refCoords = self.getCoords(refImg)
            self.refCosDec = np.cos(np.radians(refCoords.dec.value))
        except Exception as exp:
            self.msg(f"Cannot get coordinates from reference image FITS header: {exp}")
            if self.verbose: print(self.msg)
            logger.exception(self.msg)
            raise RuntimeError(self.msg)
                    
        # examine image with imExamine(), if no guide stars on first pass with the
        # default threshold, try again with half that threshold.
        
        numObj, medFW, medEll, sky, skySig = self.imExamine(refImg)
        self.msg = f"RefImage: found {numObj} stars, med FWHM={medFW:.2f} pix, med Ell={medEll:.3f}, sky={sky:.2f} +/- {skySig:.2f} adu"
        if self.verbose: print(self.msg)
        logger.info(self.msg)
        
        if numObj < self.minStars:
            newThresh = 0.5*self.threshold 
            self.msg = f"Found too few stars in reference image: {numObj} < {self.minStars}, trying threshold {newThresh:.2f}..."
            if self.verbose: print(self.msg)
            logger.warning(self.msg)
            numObj2, medFW, medEll, sky, skySig = self.imExamine(refImg,thresh=newThresh)
            if numObj2 < self.minStars:
                self.msg = f"Still found too few stars in reference image: {numObj2}, aborting science guider initialization..."
                if self.verbose: print(self.msg)
                logger.error(self.msg)
                raise RuntimeError(self.msg)
            else:
                self.msg = f"Using reduced detection threshold {newThresh:.1f}-sigma above sky"
                if self.verbose: print(self.msg)
                thresh = newThresh
        else:
            thresh = self.threshold
                    
        # build reference star catalog with findStars() store in self.refX and self.refY
        
        try:
            refX,refY = self.findStars(refImg,thresh=thresh)
            if len(refX) == 0:
                errMsg = self.msg
                self.msg = f"No guide stars found in reference image: {errMsg}"
                if self.verbose: print(self.msg)
                logger.error(self.msg)
                raise RuntimeError(self.msg)
            else:
                logger.info(f"Guider initialized for reference image {self.refImg}")
                if self.verbose: print(self.msg)
                
                # populate the reference guide star XY arrays and set the
                # guider b coefficient for the declination of the field
                
                self.refX = np.array(refX)
                self.refY = np.array(refY)
                self.guide_b = self.guide_b0/self.refCosDec

        except Exception as exp:
            self.msg = f"Guider setup failed: {exp}"
            logger.error(self.msg)
            raise RuntimeError(self.msg)
            
        
    def sciGuide(self,imgFile):
        
        # Open and read in target image
               
        # build target star catalog with findStars()
        
        # compute the shift to move the target image back to
        # the reference image position
        
        # execute the offset using the Camera.guideMove() method
        
        return False

    
       
