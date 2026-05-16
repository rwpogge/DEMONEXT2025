"""DEMONEXT Camera Control System interface class

Class to remotely operate the DEMONEXT science and guide cameras
through the MaxIm DL CCDCamera ASCOM class.

Author
------
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2024 Dec 31

Modification History
--------------------
    2024 Dec 31 - first version [rwp/osu]
    2025 Jan 01 - first live tests with telescope [rwp/osu]
    2025 Jan 06 - added guide telescope autoguider methods [rwp/osu]
    2025 Jan 24 - added gcal image type for science guiding [rwp/osu]
    2025 Jan 30 - added science() method, bug fixes [rwp/osu]
    2025 Apr 30 - bug fixes from lab testing [rwp/osu]
    2026 Mar 29 - added observatory site telemetry info [rwp/osu]
    
"""

import os
import time
import glob
import datetime

# Windows Component Object Model (COM) client module

from win32com.client import Dispatch

# pathlib for path handling

from pathlib import Path

# yaml for configuration file parsing

import yaml

# logging

import logging
logger = logging.getLogger("Camera") 

# numpy and astropy.io.fits

import numpy as np
from astropy.io import fits

# Camera Class

class Camera:
    """Camera control class
    
    Operates the science and guide cameras connected through the 
    MaxIm DL application.
        
    Methods
    -------
    __init__(cfgFile)
        initialize the Camera class instance, but do not connect to the MaxIm DL app.
       
        cfgFile: string
            full name of the YAML runtime configuration file to load.
            default: looks in $HOME for `.demonext/config/demonext.txt`
    connect()
        connect and initialize cameras
    disconnect()
        disconnect the cameras
    getCCDInfo()
        return CCD configuration and state information (returns dict)
    getInstState()
        return supplemental instrument status for FITS headers
    updateFITSHeader(fitsInfo)
        update FITS headers for the current image with instrument, site, and project info
    getFilter()
        get the current filter position
    setFilter(filtNum)
        set the filter by number as `filtNum` (0..numFilt)
    filterNum(filtName)
        return the filter number corresponding to filter name string `filtName`
    setDataDir(dataPath)
        set the raw data directory path
    getObsDate()
        return the current observing date in CCYYMMDD format
    getNextFile(imgType)
        get the name of the next FITS file of imgType to be written
    projectInfo(projID,piName,piInst,objectID)
        set the FITS header project information for data ownership and accounting
    objectID(objID)
        set the OBJECT name for the next image
    ccdTemp()
        return the CCD detector temperature in degrees C
    tecTemp()
        return the CCD thermoelectric cooler heat-sink (hot side) temperature in degrees C
    isCooling()
        return True if the CCD thermoelectric cooler is running, False if off
    tecPower()
        return the CCD thermoelectric cooler power in % of max power (0..100%)
    setPoint([setpoint])
        get/set the CCD cooler setpoint temperature
    cooldown([newSetPoint],wait=True)
        turn on the CCD thermoelectric cooler and cool it down to the operating setpoint temperature
    warmup(wait=True)
        do a controlled warmup of the CCD detector to ambient
    acquire(imgType,expTime,[filtNum])
        acquire a CCD image of `imgType` with exposure time `expTime` seconds and filter `filtNum`
    science(*args)
        acquire science images not using science guiding, `obsDef` list or individual arguments 
    bias(nimgs=1)
        acquire `nimgs` bias images (default: 1 bias image)
    dark(expTime,nimgs=1)
        acquire `nimgs` dark frames of exposure time `expTime` seconds (default: 1 bias image)
    flat(expTime,filtNum,nimgs=1)
        acquire `nimgs` flat field images of exposure time `expTime` through filter 'filtNum' (default: 1 flat image)
    guideMove(dTx,dTy)
        send a guider move
    findGuideStar()
        find a suitable guide star and exposure time
    guiderCalib()
        calibrate the guide camera (start of the night)
    guidingOff()
        disable autoguiding
    guidingOn()
        enable autoguiding
    isGuiding()
        return True if autoguiding, False if not guiding
    
    Attributes
    ----------
    connected : bool
        True if connected to MaxIm DL, false if disconnected
    dataDir : string
        full path to the raw data directory
    lastFile : string
        name of the last file written to `dataDir`
    setpoint : float
        setpoint temperature for the CCD (default: -20C)
    filterList : list of strings
        list of filter names in the filter wheel
    numFilt: integer
        number of filter postions in the filter wheel
    maxExpTime: float
        maximum allowed exposure time (usuall 1800 sec)
    projInfo : dictionary
        dictionary with observing project FITS header keywords
    siteInfo : dictionary
        dictionary with observatory site FITS header keywords (site, latitude, longitude, etc.)
    instInfo : dictionary
        dictionary with instrument setup FITS header keywords
    ccdInfo : dictionary
        dictionary with CCD setup information retrieved using getCCDInfo()
    telescope : Telescope class instance
        Telescope object to use for camera/telescope interaction
    focuser : Focuser class instance 
        Focuser object to use for camera/focuser interaction
    msg : string
        internal messages
    
    """
    
    def __init__(self,*args):
        """
        Constructor for the Camera class. 

        Parameters
        ----------
        *args :
            cfgFile : string
                YAML configuration file (including path) with camera configuation info
            
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
        needed to operate the science and guide cameras, but does not 
        yet connect to the MaxIm DL app that runs the cameras.  This 
        is done with the connect() method.

        If no runtime configuration file is given, it defaults to a file 
        named demonext.txt in the user .demonext/config/ directory 
        (default expectation).  We load it directly rather than using
        the Config class.

        """
        
        # ASCOM classes

        self.MaxImASCOM = "MaxIm.Application"
        self.ccdASCOM = "MaxIm.CCDCamera"

        # ASCOM class instances
        
        self.maxIm  = None # ASCOM MaxIm application object
        self.maxCam = None # ASCOM CCDCamera object

        # DEMONEXT class instances

        self.telescope = None # DEMONEXT telescope class
        self.focuser = None   # DEMONEXT focuser class
        self.site = None      # DEMONEXT observatory site class
        
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

            # Information for FITS headers - baseline FITS keyword set
                
            # observatory site information
                
            try:
                self.siteInfo = config["site"]
            except:
                self.siteInfo = None

            # instrument info 
                
            try:
                self.instInfo = config["instrument"]
            except:
                self.instInfo = None

            # default (engineering) project info, gets overloaded later.
                
            try:
                self.projInfo = config["project"]
            except:
                self.projInfo = None

            # science camera configuration

            try:
                self.ccdConfig = config["ccd"]
            except:
                self.ccdConfig = None

            # guide camera configuration
            
            try:
                self.gcamConfig = config["guider"]
            except:
                self.gcamConfig = None
                
            # calibration program info, overloads projInfo for calibs
                
            try:
                self.calProgram = config["calibration"]
            except:
                self.calProgram = {"PROJECT":"Calibration",
                                   "PI_Name":"Calibration",
                                   "PI_Inst":"All",
                                   "OBJECT":"Calibration"}

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

        # template camera FITS header keyword dictionary

        self.fitsHeader = {}
        for info in [self.siteInfo,self.instInfo,self.projInfo]:
            if info:
                self.fitsHeader.update(info)
            
        # Custom science CCD camera configuration - use defaults if none given in the configuration file

        # Defaults if no config information:

        self.setpoint = -20.0    # TEC setpoint in C
        self.maxExpTime = 1800.0 # seconds
        self.ccdXBin = 1
        self.ccdYBin = 1
        
        # camera filter wheel defaults
        
        self.fwStepTime = 1.2 # seconds to move one position
          
        # Update from the runtime config file as needed
        
        if self.ccdConfig:
            if "Setpoint" in self.ccdConfig:
                self.setpoint = self.ccdConfig["Setpoint"]
            if "MaxExpTime" in self.ccdConfig:
                self.maxExpTime = self.ccdConfig["MaxExpTime"]
            if "Binning" in self.ccdConfig:
                self.ccdXBin = self.ccdConfig["Binning"][0]
                self.ccdYBin = self.ccdConfig["Binning"][0]
            if "FWStepTime" in self.ccdConfig:
                self.fwStepTime = self.ccdConfig["FWStepTime"]

        # Guide camera configuration info
        
        if self.gcamConfig:
            if "TELESCOP" in self.gcamConfig:
                self.guideScope = self.gcamConfig['TELESCOP']
            if "INSTRUME" in self.gcamConfig:
                self.guideCam = self.gcamConfig['INSTRUME']
            if "FILTER" in self.gcamConfig:
                self.guideFilter = self.gcamConfig['FILTER']
            if "Aggressiveness" in self.gcamConfig:
                self.aggressiveness = self.gcamConfig['Aggressiveness']
            if "ExpTimes" in self.gcamConfig:
                self.guiderExpTimes = self.gcamConfig['ExpTimes']
                
        else:
            self.guideScope = 'None'
            self.guideCam = 'None'
            self.guideFilter = 'None'
            self.aggressiveness = 7
            self.guiderExpTimes = [1,2,5,10,20,30,60]  # exposure times to use for guiding
            
        # Runtime flags

        self.connected = False

        # valid image type dictionary, 1 = open-shutter, 0 = close-shutter

        self.imgTypes = {"sci":1,
                         "bias":0,
                         "dark":0,
                         "flat":1,
                         "gcal":1}

        # does image type require a filter selection?
        
        self.reqFilter = {"sci":True,
                          "bias":False,
                          "dark":False,
                          "flat":True,
                          "gcal":True}
        
        # next file to be written (created with getNextFile() method)
        
        self.nextFile = None
        
        # time delays for various operations

        self.connectDelay = 5 # seconds - longer for MaxIm and CCD than telescope
        self.dispatchDelay = 5 # seconds
        self.timeDelay = 2 # seconds
        self.queryCadence = 0.1 # seconds - fastest cadence of CCD camera queries
        self.guideCadence = 0.5 # seconds - fastest cadence of guide camera queries
        
        # Useful boolean translation dictionaries

        self.OnOff = {True:"On",False:"Off"}
        self.YesNo = {True:"Yes",False:"No"}

        # CCD camera status codes returned by MaxIm.CCDCamera.CameraStatus
        # Note that not all status codes are used or reported by all cameras

        self.statusCodes = {0:"Camera Not Connected",
                            1:"Camera reporting an error",
                            2:"Camera idle",
                            3:"Camera acquiring a Science image",
                            4:"Camera reading out",
                            5:"Camera writing to computer memory",
                            6:"Camera flushing sensor",
                            7:"Camera waiting for external trigger signal",
                            8:"Waiting for MaxIm to be ready to receive data",
                            9:"Camera waiting until time to acquire next image",
                            10:"Camera acquiring a Dark image using Simple Auto Dark",
                            11:"Camera acquiring a Bias image",
                            12:"Camera acquiring a Dark Image",
                            13:"Camera acquiring a Flat Image",
                            15:"Camera waiting on Filter Wheel"}

        # guide camera calibration state codes returned by MaxIm.CCDCamera.GuiderCalState

        self.calStates = {0:"Guide Camera Not Calibrated",
                          1:"Guide Camera Calibration in progress",
                          2:"Guide Camera Calibration Complete",
                          3:"Guide Camera Calibration Failed"}

        # operation timeouts

        self.coolingTimeout = 1200. # CCD cooling timeout 20 minutes cool down is ~10 minutes for dT=45C from ambient
        self.warmingTimeout = 600.  # CCD warming timeout 10 minutes, warm up is ~5 minutes for dT=45C from ambient
        self.minExpTimeout = 30.0   # minimum exposure timeout = 2*(max filter move time + full-frame readout time)
        
        # filter info

        self.filterList = [] # list of filters, load from MaxIm at connect time or self.getFilterList()
        self.numFilt = 0
        
        # other stuff

        self.getObsDate() # set the observing date at startup
        
        self.coolingTolerance = 0.2 # tolerance in degrees C for declaring "CCD at operating temperature"
        self.warmupTolerance = 2.0  # tolerance in degrees C for declaring "CCD at ambient temperature"
        
        self.coolerCadence = 3.0 # TEC cooling/warming query cadence in seconds
        
        self.ccdInfo = {} # CCD parameter dictionary (see getCCDInfo() method)
        
        # internal messages

        self.msg = ""


    # Methods

    #--------------------------------
    #
    # app startup and ASCOM methods
    #

    def connect(self):
        """
        Connect to MaxIm DL app and camera controller

        Raises
        ------
        RuntimeError
            Raised if it cannot connect with MaxIM DL ASCOM services or
            gets errors on setting up the cameras.

        Returns
        -------
        None.
        
        Description
        -----------
        Creates Windows Common Object Module (COM) client ASCOM interface
        instances the MaxIm Application and CCDCamera controller apps
        and connects the ASCOM services we need to run the cameras.
        
        The MaxIm DL app will be launched if not already running, which is
        why we use wait for dispatchDelay and connectDelay to give them
        time to lauch if needed

        We also set the ASCOM LockApp and DisableAutoShutdown properties True
        on the application and camera objects.  LockApp=True ensures that
        the MaxIm app keeps running even if all COM objects close.  
        DisableAuthShutdown=True ensures that the camera is not disconnected
        automatically by MaxIm if idle for a long time.

        See Also
        --------
        disconnect
        """

        # instantiate MaxIM DL application COM client
        
        try:
            self.maxim = Dispatch(self.MaxImASCOM)
            time.sleep(self.dispatchDelay)
            self.connected = True
            logger.info("Started MaxIm DL app")
        except Exception as exp:
            msg = f"Cannot start {self.MaxImASCOM} COM client: {exp}"
            logger.exception(msg)
            self.maxim = None
            self.connected = False
            self.telConnected = False
            raise RuntimeError(msg)

        # LockApp=True ensures MaxIm keeps running even if all COM objects close
        
        self.maxim.LockApp = True

        # Ask MaxIM DL to connect to the telescope controller

        try:
            self.maxim.TelescopeConnected = True
            self.telConnected = True
            logger.info("MaxIM DL connected to the telescope controller")
        except Exception as exp:
            self.telConnected = False
            msg = f"Cannot connect MaxIm DL to the telescope controller: {exp}"
            logger.exception(msg)
            self.connected = False
            raise RuntimeError(msg)
        
        # instantiate a MaxIm CCDCamera COM client

        try:
            self.ccd = Dispatch(self.ccdASCOM)
            time.sleep(self.dispatchDelay)
            self.connected = True
            logger.info("MaxIM DL camera controller app started")
        except Exception as exp:
            msg = f"Cannot start {self.MaxImASCOM} COM client: {exp}"
            logger.exception(msg)
            self.ccd = None
            self.connected = False
            raise RuntimeError(msg)

        # link MaxIm with the cameras (science and guider)

        try:
            self.ccd.LinkEnabled = True
            logger.info("CCD and Guide Cameras linked to MaxIM DL")
        except Exception as exp:
            msg = f"Cannot link cameras to MaxIm DL - check power and physical connections: {exp}"
            logger.exception(msg)
            self.ccd = None
            self.connected = False
            raise RuntimeError(msg)

        # Set DisableAutoShutdown so the camera is not disconnected when idle

        self.ccd.DisableAutoShutdown = True
        
        # we're connected, some basic setup of the camera
        
        self.connected = True

        try:
            ccdTemp = self.ccd.Temperature
            if ccdTemp > 100.0: # Camera FPGA still booting sleep self.connectDelay
                time.sleep(self.connectDelay)
                ccdTemp = self.ccd.Temperature

            tecState = self.ccd.CoolerOn
            tecTemp = self.ccd.AmbientTemperature # TEC base/heat sink temperature on FLI camers
            tecPower = self.ccd.CoolerPower
            
            # default settings
            
            self.ccd.TemperatureSetpoint = self.setpoint
            self.ccd.BinX = self.ccdXBin
            self.ccd.BinY = self.ccdYBin

            if tecState:
                logger.info(f"CCD Cooler ON, tecPower={tecPower:.1f}% setPoint={self.setpoint:.1f}C ccdTemp={ccdTemp:.2f}C, tecTemp={tecTemp:.2f}C")
            else:
                logger.info(f"CCD Cooler OFF, setPoint={self.setpoint:.1f}C ccdTemp={ccdTemp:.2f}C, tecTemp={tecTemp:.2f}C")
        except Exception as exp:
            msg = f"Errors attempting to set startup CCD configuration: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # Get the filter ID table from MaxIm

        try:
            self.filterList = self.ccd.FilterNames
            self.numFilt = len(self.filterList)
            logger.info("Retrieved filter list from MaxIm")
        except Exception as exp:
            msg = f"Cannot read filter table from MaxIm: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
        # populate the ccdInfo dictionionary
        
        self.getCCDInfo()
        
        # all done!
        
        logger.info("MaxIm DL Startup Complete")


    def disconnect(self):
        """
        Disconnect from the CCD controller and remove
        the ASCOM object instances.

        Raises
        ------
        RuntimeError
            Raised if there are problems disconnectding.

        Returns
        -------
        None.
        
        See Also
        --------
        connect
        """

        if self.maxim.TelescopeConnected:
            logger.info("Disconnecting the telescope from MaxIm")
            try:
                self.maxim.TelescopeConnected = False
                time.sleep(self.connectDelay)
            except Exception as exp:
                msg = f"Cannot disconnect the telescope: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)

        if self.ccd.LinkEnabled:
            logger.info("Unlinking science and guide cameras from MaxIm")
            try:
                self.ccd.LinkEnabled = False
                time.sleep(self.connectDelay)
            except Exception as exp:
                msg = f"Cannot unlink cameras from MaxIm: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)

        self.maxim.LockApp = False

        # release the ASCOM classes
        
        self.maxim = None
        self.ccd = None
        self.connected = False

        logger.info("Camera disconnection complete")


    #------------------------------------
    #
    # Camera info methods
    #
    
    def getCCDInfo(self):
        """
        Get science CCD camera configuration information

        Returns
        -------
        dict
            ccdInfo dictionary with camera information.

        """
        
        self.ccdInfo = {}
        
        self.ccdInfo['sizeX'] = self.ccd.CameraXSize
        self.ccdInfo['sizeY'] = self.ccd.CameraYSize
        self.ccdInfo['pixSizeX'] = self.ccd.PixelSizeX
        self.ccdInfo['pixSizeY'] = self.ccd.PixelSizeY
        self.ccdInfo['binX'] = self.ccd.BinX
        self.ccdInfo['binY'] = self.ccd.BinY
        self.ccdInfo['startX'] = self.ccd.StartX
        self.ccdInfo['startY'] = self.ccd.StartY
        self.ccdInfo['numX'] = self.ccd.NumX
        self.ccdInfo['numY'] = self.ccd.NumY

        # on first read, camera can read a false number, give the camera FPGA time to spin up

        ccdTemp = self.ccd.Temperature
        if ccdTemp > 100.0: # camera FPGA still getting going, sleep 2s and try again
            time.sleep(self.timeDelay)
            
        self.ccdInfo['CCDTemp'] = self.ccd.Temperature
        self.ccdInfo['TECTemp'] = self.ccd.AmbientTemperature
        self.ccdInfo['setPoint'] = self.ccd.TemperatureSetpoint
        self.ccdInfo['TECPower'] = self.ccd.CoolerPower
        self.ccdInfo['TECState'] = self.OnOff[self.ccd.CoolerOn]

        return self.ccdInfo        

    #------------------------------------
    #
    # FITS header methods
    #
    
    def getInstStatus(self):
        """
        Get instrument status for FITS headers
        
        Returns
        -------
        instInfo : dict
            Dictionary with instrument status information in FITS format.
            
        Description
        -----------
        Queries the camera and focuser (if linked) and returns additional
        information for inclusing in image FITS headers that is not captured 
        by MaxIm DL by default.
        
        See Also
        --------
        updateFITSHeader
        """

        instInfo = {}
            
        # CCD Cooler information

        instInfo['CCDTEMP'] = self.ccd.Temperature
        instInfo['TECTEMP'] = self.ccd.AmbientTemperature 
        instInfo['SETPOINT'] = self.ccd.TemperatureSetpoint
        instInfo['TECSTATE'] = self.OnOff[self.ccd.CoolerOn]
        instInfo['TECPOWER'] = self.ccd.CoolerPower
        
        # Focuser information

        if self.focuser is not None:
            instInfo['FOCUSPOS'] = self.focuser.getPos()
            instInfo['MIRROR_T'] = self.focuser.getMirrorTemp()
            instInfo['AMBIENT'] = self.focuser.getAmbientTemp()

        return instInfo


    def updateFITSHeader(self,fitsInfo):      
        """
        Update MaxIm FITS header with additional keywords
        
        Parameters
        ----------
        fitsInfo : dict
            dictionary with FITS header info to load into MaxIm DL.

        Raises
        ------
        RuntimeError
            Raised if there are problems uploading FITS keywords.

        Returns
        -------
        None.
        
        Description
        -----------
        Uploads the contents of the fitsInfo dictionary to the
        MaxIm.CCDCamera app for inclusion in image FITS headers for
        the image just read into MaxIm's memory buffer.  It provides
        FITS header information not captured by MaxIm proper.
        
        See Also
        --------
        getInstStatus
        """
        
        for key,value in fitsInfo.items():
            try:
                self.ccd.setFITSKey(key,value)
            except Exception as exp:
                msg = f"FITS keyword '{key:8s} = {value}' raised exception {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)

    #------------------------------------
    #
    # Filter wheel methods
    #

    def filterNum(self,filtName):
        """
        Filter position number corresponding to named filter
        
        Parameters
        ----------
        filtName : string
            filter name string.

        Returns
        -------
        integer
            Filter wheel position of the named filter, 0..numFilt-1, or -1 if
            the named filter is not in the filter wheel.
            
        Description
        -----------
        Return the filter wheel position with the named filter.
        
        The `MaxIm.CCDCamera Expose()` method requires setting filter by
        position number not by name. This function provides
        a convenient back translator for applications using this class.

        Fault conditions that return -1 for the filter number:
         * `filterList` is empty (try `getFilterList()` first)
         * `filtName` does not match any filter list entries (case insensitive)
         * (unlikely) `filterList.index()` raised an exception
        
        The filter name matching test is case-insensitive.
         
        Note
        ----
        The filter table on the MaxIm DL camera tool lists filter positions
        running from 1..numFilt, whereas the filter wheel itself labels 
        the physical filter positions on the wheel from 0..numFilt-1 with engraved
        numbers, and ASCOM's Filter property also numbers filters from
        0..numFilt-1. This function is designed to shield users from making
        off-by-one errors when selecting filters by always selecting by name
        instead of by [index-ambiguous] wheel position numbers.

        See Also
        --------
        getFilterList, getFilter, setFilter
        """
        
        if len(self.filterList)==0:
            return -1

        testList = [s.lower() for s in self.filterList]
        testFilt = filtName.lower()
        
        if testFilt in testList:
            try:
                fnum = testList.index(testFilt)
                return fnum
            except:
                return -1

        else:
            return -1
    
        
    def getFilterList(self):
        """
        Retrieve the names of the filters in the filter wheel from
        MaxIm DL.

        Raises
        ------
        RuntimeError
            Raised if it cannot read the table from the MaxIM app.

        Returns
        -------
        list
            List of filter name strings.

        See Also
        --------
        getFilter, setFilter, filterNum
        """
        try:
            self.filterList = self.ccd.FilterNames
        except Exception as exp:
            msg = f"Cannot read filter table from MaxIm: {exp}"
            self.filterList = []
            self.numFilt = 0
            logger.exception(msg)
            raise RuntimeError(msg)

        self.numFilt = len(self.filterList)
        return self.filterList
    
    
    def getFilter(self):
        """
        Return the number of the filter in front of the CCD

        Raises
        ------
        RuntimeError
            Raised if the filter wheel position query fails.

        Returns
        -------
        integer
            Number of the filter in front of the CCD
            range: 0..numFilt-1
            
        Description
        -----------
        The filter wheel labels positions from 0 to numFilt-1.

        See Also
        --------
        setFilter, getFilterList, filterNum
        """
        try:
            return self.ccd.Filter
        except Exception as exp:
            msg = f"Cannot query current filter position: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
    
    def setFilter(self,reqFilt):
        """
        Put the requested filter in front of the CCD by number

        Parameters
        ----------
        reqFilt : integer
            requested filter wheel position, must be 0..numFilt-1
            
        Raises
        ------
        ValueError
            Raised if reqFilt is outside the range 0..numFilt-1
        RuntimeError
            Raised on errors setting or querying the filter wheel.

        Returns
        -------
        None.

        Description
        -----------
        Puts the requested numbered filter in front of the CCD.  Filters positions
        are numbered 0..numFilt-1 in code and physically on the filter wheel)
        and motion is unidirectional from smaller to larger slot number.
        Because the ASCOM Filter motion is non-blocking when used directly 
        like this, we have to inject a time delay before returning to ensure 
        the requested motion is complete.
        
        The time to move between positions is fwStepTime. If motion is 
        positive, e.g., from filter 2 to 3, the delay will be fwStepTime.
        However, the reverse motion from filter 3 to 2 takes fwStepTime*(numFilt-1)
        because the filter mechanism must travel the long way around from 3 to 2.
        
        See Also
        --------
        getFilter, getFilterList, filterNum
        """
        # validate filter ID, range is 0 .. self.numFilt-1
        if reqFilt < 0 or reqFilt > self.numFilt-1:
            msg = f"Invalid filter number {reqFilt} must be 0..{self.numFilt-1}"
            logger.exception(msg)
            raise ValueError(msg)
        
        # get the current filter in position
        
        try:
            curFilt = self.ccd.Filter
        except Exception as exp:
            msg = f"Cannot query current filter position: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
            
        # if reqFilt is curFilt, we are already in place, return right away
        
        if reqFilt == curFilt:
            return
        
        # The ASCOM Filter motion is non-blocking and the filter
        # wheel is one-way (lower to higher numbers), so the time to
        # move between filters is how long we wait before returning
        # to ensure the motion is completed to avoid race conditions.
        
        dFilt = reqFilt - curFilt
        if dFilt > 0:
            moveTime = self.fwStepTime * dFilt
        else:
            moveTime = self.fwStepTime * (self.numFilt + dFilt)
        
        # do it
        
        try:
            self.ccd.Filter = reqFilt
            time.sleep(moveTime)
        except Exception as exp:
            msg = f"Cannot selection requested filter {reqFilt}: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
        return
        
        
    #------------------------------------
    #
    # Directory and FITS file methods
    #

    def setDataDir(self,*args):
        """
        Set/get the full path of the data directory

        Parameters
        ----------
        *args : dataDir
            string with the full path to the data directory.
            
        Raises
        ------
        RuntimeError
            Raised if it cannot create a new data directory if needed.

        Returns
        -------
        string
            Full qualified path to the data directory.
            
        Description
        -----------
        If given without arguments, dataDir() returns the current data 
        directory path.  If an argument is given, it attempts to change
        the data directory path and redefine the dataDir property.
        
        If the new dataDir does not exist, it attempts to create it.
        If creation fails, it retains the old data directory and raises
        a RuntimeError exception.
        
        If root is not part of the directory path given, it will
        default to the user home directory as a safety measure so
        that it has a place it knows it can write data.
        """

        # if no arguments, return the current data directory path
        
        if len(args) == 0:
            return self.dataDir

        # we have an argument, interpret as a new data directory

        newDir = args[0]

        # if path has no root, assume relative to user home

        if len(Path(newDir).root) == 0:
            dataDir = str(Path.home() / newDir)
        else:
            dataDir = newDir
            
        if not Path(dataDir).exists():
            try:
                Path(dataDir).mkdir()
                logger.info(f"Created new data directory {dataDir}")
            except Exception as exp:
                msg = f"Cannot create new data directory {dataDir}: {exp}"
                logger.exceptions(msg)
                raise RuntimeError(msg)
        
        self.dataDir = dataDir
        logger.info(f"Raw data directory is now {dataDir}")

        return self.dataDir


    def getObsDate(self):
        """
        Return the observing date string.
        
        Returns
        -------
        string
            Observing date in CCYYMMDD format.
            
        Description
        -----------
        Observing dates run from noon to noon local time and are formatted 
        CCYYMMDD.  These are used for logs and filenames to keep all data
        from a given night together with data taken the afternoon before
        and the morning after.
        
        """

        if float(datetime.datetime.now().strftime("%H")) < 12.0:  # before noon
            self.obsDate = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
        else:
            self.obsDate = datetime.date.today().strftime("%Y%m%d")
        return self.obsDate


    def getNextFile(self,fileType):
        """
        Return the name of the next file of fileType to be written on this observing date

        Parameters
        ----------
        fileType : string
            File type to be created - prefix for the filename 
            (e.g., sci, bias, flat, etc.).

        Raises
        ------
        RuntimeError
            If a new data directory is needed but cannot be created.
            
        Returns
        -------
        string
            Full qualified path to the next file to be written and also
            stores this value in the nextFile property

        Description
        -----------
        Constructs the full qualfied name of the next file of fileType to be written
        in the named data directory for the current observing date:

          /dataDir/obsDate/<fileType><obsDate>.####.fits

        where:
           /dataDir/ is the full qualified base data directory path in self.dataDir
           /obsDate/ is the observing date CCYYMMDD format auto generated by self.obsDate()
           #### is a 4-digit file number, 0001 through 9999

        Each time nextFile is called it checks the obsDate, which runs
        noon to noon local time, to make sure it catches a change in
        the observing date transparently.  It then combines this with
        the base date directory (self.dataDir) to get the full
        qualified data path (/dataDir/obsDate/).

        If /dataDir/obsDate/ exists, it searches for all instances of
        <sci>*.fits and counts them. The next file has index
        numFiles+1.  File counting is done using the glob.glob()
        method.

        If /dataDir/obsDate/ does not exist it creates it.
        
        See Also
        --------
        setDataDir, getObsDate
        """

        obsNow = self.getObsDate()
        
        dataPath = Path(self.dataDir) / obsNow
        
        if not dataPath.exists():
            logger.info(f"Creating new data directory for {obsNow}: {str(dataPath)}")
            try:
                dataPath.mkdir()
            except Exception as exp:
                msg = f"Cannot create new data directory {str(dataPath)}: {exp}"
                logger.exceptions(msg)
                raise RuntimeError(msg)

        files = glob.glob(str(dataPath / f"{fileType}*.fits"))
        nextNum = len(files) + 1
        self.nextFile = str(dataPath / f"{fileType}{obsNow}.{nextNum:04d}.fits")
            
        return self.nextFile

    #------------------------------------
    #
    # Project info handling methods
    #

    def projectInfo(self,projID,piName,piInst,objectID):
        """
        Update project info for the next program

        Parameters
        ----------
        projID : string
            Project ID code for the program.
        piName : string
            Name of the Project PI.
        piInst : string
            Name of the PI's institution.
        objectID : string
            Name of the object to be observed.

        Returns
        -------
        None.

        Description
        -----------
        Updates the project information that goes into the image FITS headers
        to identify the project and owner for time accounting and program
        tracking.  The OBJECT keyword can be overloaded without changing
        the program tracking info using the `objectID` method.
        
        See Also
        --------
        objectID
    
        """
        self.projInfo["PROJECT"] = projID
        self.projInfo["PI_NAME"] = piName
        self.projInfo["PI_INST"] = piInst
        self.projInfo["OBJECT"] = objectID
        
        
    def objectID(self,objectID):
        """
        Change the OBJECT info for the FITS header

        Parameters
        ----------
        objectID : string
            New OBJECT name for the FITS header.

        Returns
        -------
        None.
        
        Description
        -----------
        Convenience function to only change the OBJECT FITS header item 
        in the projInfo dictionary.

        See Also
        --------
        projectInfo
        
        """
        self.projInfo["OBJECT"] = objectID
        

    #------------------------------------
    #
    # CCD camera cooler control methods
    #

    def ccdTemp(self):
        """
        Read the CCD detector temperature

        Raises
        ------
        RuntimeError
            Raised if it cannot read the detector temperature.

        Returns
        -------
        ccdTemp : float
            Temperature of the CCD detector in degrees C.

        See Also
        --------
        tecTemp, setPoint, tecPower, isCooling, cooldown, warmup
        """

        try:
            ccdTemp = self.ccd.Temperature
            return ccdTemp
        except Exception as exp:
            msg = f"Cannot read CCD temperature: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)


    def tecTemp(self):
        """
        Read the CCD thermoelectric cooler (TEC) base temperature

        Raises
        ------
        RuntimeError
            Raised if it cannot read the TEC/heatsink base temperature.

        Returns
        -------
        tecTemp : float
            Temperature of the TEC base in degrees C.

        Description
        -----------      
        Reads and returns the temperature of the thermoelectric cooler
        base at the heat sink. The ASCOM property is AmbientTemperature,
        but in Finger Lakes CCDs, the "ambient" sensor is located between
        the hot-side of the Peltier cooler and the heat sink.
        
        See Also
        --------
        ccdTemp, tecPower, setPoint, isCooling, cooldown, warmup
        """

        try:
            tecTemp = self.ccd.AmbientTemperature
            return tecTemp
        except Exception as exp:
            msg = f"Cannot read TEC base temperature: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        
    def tecPower(self):
        """
        Read the CCD thermoelectric cooler power

        Raises
        ------
        RuntimeError
            Raised if it cannot read the TEC power from the CCD

        Returns
        -------
        tecPower : float
            TEC power in percentage 0..100%

        Description
        -----------
        Reads and returns the TEC power in units of percent of maximum
        power, 0..100%.  Even when cooling is off the TEC stage draws
        minimal power (~few percent)

        See Also
        --------
        isCooling, tecTemp, ccdTemp, cooldown, warmup
        """

        try:
            tecPower = self.ccd.CoolerPower
            return tecPower
        except Exception as exp:
            msg = f"Cannot read TEC power: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        

    def isCooling(self):
        """
        Is the CCD thermoelectric cooler powered on and cooling?

        Raises
        ------
        RuntimeError
            Raised if it cannot read the TEC power state.

        Returns
        -------
        boolean
            True if CCD cooling is ON, False if cooling is OFF.

        See Also
        --------
        tecPower, ccdTemp, tecTemp, cooldown, warmup
        """
        try:
            return self.ccd.CoolerOn
        except Exception as exp:
            msg = f"Cannot query CCD cooling state on/off: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        

    def setPoint(self,*args):
        """
        Set/Get the CCD cooler setpoint temperature

        Parameters
        ----------
        *args
            setpoint : float
                new setpoint temperature in degrees C.

        Raises
        ------
        ValueError
            if the setpoint temperature is invalid.
        RuntimeError
            if the setpoint temperature cannot be read or changed.

        Returns
        -------
        float
            CCD cooler setpoint temperature in degrees C.

        Description
        -----------
        If no arguments are given, reports the setpoint temperature
        (self.setpoint).  If given setPoint is valid, changes the
        self.setpoint property.

        This function does not turn cooling on if the TEC is off, but
        if it is on, changing the setpoint temperature will instruct
        the TEC to cool to the new setpoint.

        The FLI CCD camera TEC is rated to run the CCD at a fixed
        temperature no more than 50C below ambient.  A typical
        setpoint for operations is -20C, the default set when
        the Camera class is initialized.  This default can be
        changed with the "setpoint" parameter in the CCD: block
        of the runtime configuration file.
        
        See Also
        --------
        cooldown, isCooling, ccdTemp, tecTemp, tecPower, warmup
        """

        # no arguments, report the setpoint
        
        if len(args) == 0:
            return self.setpoint

        try:
            newSetPoint = float(args[0])
        except Exception as exp:
            msg = f"setPoint(): {args[0]} invalid: {exp}"
            logger.exception(msg)
            raise ValueError(msg)

        self.setpoint = newSetPoint

        try:
            self.ccd.TemperatureSetpoint = self.setpoint
            logger.info(f"Changed CCD cooler set point: {self.setpoint:.1f}C")
        except Exception as exp:
            msg = f"Cannot change CCD coolr set point: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)


    def cooldown(self,*args,wait=True):
        """
        Cool the CCD to the setpoint temperature.

        Parameters
        ----------
        newSetPoint : float, optional
            New setpoint temperature to cool the CCD to. The default is `setpoint`.
        wait : boolean, optional
            Wait for CCD to reach the operating setpoint temperature.

        Raises
        ------
        RuntimeError
            if it cannot start the cooldown.

        Returns
        -------
        None.

        Description
        -----------
        Instructs the CCD to cool to operating setpoint temperature.
        
        If given with no arguments, uses the default setpoint temperature
        defined at runtime (internal or with the runtime configuration file).
        An optional argument is to override the default setpoint temperature
        with a custom value.

        Typical cooling time is about 10 minutes to cool by about 45C
        from ambient (+25C ambient to -20C operating). The default
        setpoint is defined at runtime in the configuration file
        (backed up by a hardcoded default).  It can be changed
        with self.setPoint().

        By default this method does not return until the CCD setpoint
        temperature has been reached. However, it is possible to run
        this asynchronously by setting `wait=False`, and then
        monitoring using the self.ccdTemp() method.
        
        See Also
        --------
        warmup, isCooling, setPoint, ccdTemp, tecTemp, tecPower
        """

        # see if we are given a new setpoint
        
        if len(args) > 0:
            newSetPoint = args[0]
        else:
            newSetPoint = None
            
        # query CCD cooling state.  If already running and not given
        # a new setpoint, return now
        
        try:
            isCooling = self.ccd.CoolerOn
            if isCooling and not newSetPoint:
                return

        except Exception as exp:
            msg = f"Cannot read CCD cooler on/off state: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # log start of cooling

        if newSetPoint:
            self.setpoint = newSetPoint
            
        if wait:
            logger.info(f"Starting CCD cooldown to {self.setpoint:.1f}C")
        else:
            logger.info(f"Starting background CCD cooldown to {self.setpoint:.1f}C")

        try:
            self.ccd.TemperatureSetpoint = self.setpoint
            self.ccd.CoolerOn = True
            if not wait:
                return

        except Exception as exp:
            msg = f"Cannot start CCD cooldown: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # If we got here, we are waiting until we reach the setpoint or timeout

        startTemp = self.ccd.Temperature # starting temperature
        deltaT = abs(startTemp - self.setpoint)
        coolingTime = 0.0 # initialize the cooldown timer

        t0 = time.time()
        
        while (deltaT > self.coolingTolerance and coolingTime < self.coolingTimeout):
            nowTemp = self.ccd.Temperature
            deltaT = abs(nowTemp - self.setpoint)
            coolingTime = time.time() - t0
            time.sleep(self.coolerCadence)

        # done, did we reach temperature or timeoput?

        coolingTime = time.time() - t0
        if coolingTime > self.coolingTimeout:
            logger.warning(f"CCD did not reach setpoint {self.setpoint:.1f}C after {self.coolingTimeout/60.0:.1f} minutes")
        else:
            logger.info(f"CCD has reached operating temperature of {self.setpoint:.1f}C")

        return

    
    def warmup(self,wait=True):
        """
        Controlled warmup of the CCD camera to ambient

        Parameters
        ----------
        wait : boolean, optional
            Wait for CCD to reach ambient temperature. The default is True.  
            
        Raises
        ------
        RuntimeError
            Raised if it cannot initiate the warmup.

        Returns
        -------
        None.
        
        Description
        -----------
        Instructs the CCD to warm up to ambient temperature in a
        controlled way.  Simply turning off TEC power for a cold
        (typically -20C) CCD could cause a damaging thermal shock
        though most modern CCD cameras have long enough thermal times
        this is more long-term protection against repeated thermal
        "shocks" than a single-point failure.

        Typical controlled warmup time is about 5 minutes from -20C to
        25C, about twice as fast as cooldown.  We adopt as the
        "ambient" temperature setpoint either of 2 sources.
          * If the focuser is linked, read the telescope ambient temperature
          * If no focuser, read the camera TEC heat sink temperature - 10C
        The heat sink does not directly measure ambient because it is warm
        when the cooler is running at cooling power (as it should).  The -10
        is a good number for 20C ambient with CCD at -20C operating.

        By default this method does not return until the CCD reaches
        within self.warmupTolerance of ambient.  However, it is
        possible to run this asynchronously by setting "wait=False",
        and then monitoring using the self.ccdTemp() method.
        
        See Also
        --------
        cooldown, isCooling, setPoint, ccdTemp, tecTemp, tecPower
        """

        # query CCD cooling state.  If already off, return
        
        try:
            isCooling = self.ccd.CoolerOn
            if not isCooling:
                return

        except Exception as exp:
            msg = f"Cannot read CCD cooler on/off state: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # log start of warmup

        if wait:
            logger.info("Starting CCD controlled warmup to ambient")
        else:
            logger.info("Starting background CCD controlled warmup to ambient")

        # two ways to measure "ambient"
        #  1) if focuser is linked, use the telescope ambient temperature
        #  2) if no focuser, use the heatsink temp - 10C since the heat sinke
        #      runs 8-10C above ambient in when running at ~80% power cold
        
        if self.focuser:
            warmPoint = self.focuser.getAmbientTemp()
        else:
            warmPoint = self.ccd.AmbientTemperature - 10.0 # "ambient" = "heat sink"
            
        try:
            self.ccd.TemperatureSetpoint = warmPoint
            self.ccd.CoolerOn = True  
            if not wait:
                return

        except Exception as exp:
            msg = f"Cannot start CCD controlled warmup: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # If we got here, we are waiting until we reach the ambient or timeout

        startTemp = self.ccd.Temperature 
        deltaT = abs(startTemp - warmPoint)
        warmingTime = 0.0 

        t0 = time.time()
        
        while (deltaT > self.warmupTolerance and warmingTime < self.warmingTimeout):
            nowTemp = self.ccd.Temperature
            deltaT = abs(nowTemp - warmPoint)
            warmingTime = time.time() - t0
            time.sleep(self.coolerCadence)

        # done, did we reach ambient or timeout?  If timeout keep the cooler on in case

        warmingTime = time.time() - t0
        if warmingTime > self.warmingTimeout:
            logger.warning(f"CCD did not reach ambient after {self.warmingTimeout/60.0:.1f} minutes")
            return
        else:
            logger.info("CCD has reached ambient temperature")
            
        # we are near enough to ambient to turn off the cooler safely
        
        self.ccd.CoolerOn = False

        return

    #------------------------------------
    #
    # CCD image acquisition methods
    #
    # acquire() method does all the work
    #
    # bias(), dark(), etc. call acquire() for efficient calibrations
    #

    def acquire(self,*args,**kwargs):
        """
        Acquire a CCD image

        Parameters
        ----------
        *args
           imgType : string
               type of image to acquire, one of "sci","bias","dark","flat"
           expTime : float
               exposure time in seconds, 0 to self.maxExpTime
           filtNum : integer
               filter position by number use None or omit if no filter 
        **kwargs
            save: boolean
                True will save the image as FITS, False will not save.
                save is TRUE by default.
                
        Raises
        ------
        ValueError
            Raised if invalid arguments.
        RuntimeError
            Raised if errors occur during image acquision

        Returns
        -------
        None.

        Description
        -----------
        Acquire an image with the science CCD camera. Uses the MaxIm.CCDCamera.Expose()
        method, which requires a filter for "light" images that open the shutter.
        This method takes care of all bookkeeping for FITS headers, exposure tracking,
        creating of filenames, and error handling.  
        
        See Also
        --------
        bias, dark, flat
        """

        # by default, save all images as FITS
        
        saveFile = True
        
        # arguments passed
        
        if len(args) == 3:
            imgType = args[0]
            expTime = args[1]
            filtNum = args[2]
        elif len(args) == 2:
            imgType = args[0]
            expTime = args[1]
            filtNum = None
        elif len(args) == 1:
            imgType = args[0]
            expTime = 0.0
            filtNum = None
        else:
            msg = f"acquire() got {len(args)} arguments, must be 1..3"
            logger.error(msg)
            raise ValueError(msg)

        if len(kwargs) > 0:
            for key, val in kwargs.items():
                if key.lower() == "save":
                    saveFile = val
                else:
                    msg = f"Unrecognized kwarg {key}, must be [save,...]"
                    logger.exception(msg)
                    raise ValueError(msg)
                    
        # validation

        # must give a valid image type
        
        if imgType in self.imgTypes:
            light = self.imgTypes[imgType]
        else:
            msg = f"Invalid image type {imgType} must be one of {list(self.imgTypes.keys())}"
            logger.error(f"acquire(): {msg}")
            raise ValueError(msg)

        # exposure time must be 0 to self.maxExpTime
        
        if expTime < 0 or expTime > self.maxExpTime:
            msg = f"Invalid exposure time {expTime:.2f}, must be 0..{int(self.maxExpTime)} sec"
            logger.error(f"acquire(): {msg}")
            raise ValueError(msg)

        # only validate the filter if imgType requires a filter
        
        if self.reqFilter[imgType]:
            if filtNum < 0 or filtNum > len(self.filterList)-1:
                msg = f"Invalid filter position {filtNum}, must be 0 to {self.numFilt-1}"
                logger.error(f"acquire(): {msg}")
                raise ValueError(msg)

        # passed first level of validation, begin setup of the exposure
       
        if light:
            logger.info(f"Starting {expTime:.1f} sec {imgType} image with the {self.filterList[filtNum]} filter")
        else:
            if expTime > 0:
                logger.info(f"Starting {expTime:.1f} sec {imgType} image")
            else:
                logger.info(f"Starting {imgType} image")

        # camera status at the start of the sequence
        
        lastState = self.ccd.CameraStatus

        # Create a new working FITS header by copying the template and overloading it
        # with header data not captured by MaxIm DL for upload later.  These snapshots
        # capture data the start of the exposure.

        newHeader = self.fitsHeader
        newHeader.update(self.projInfo) # overload default project info

        if not self.telescope is None:
            newHeader.update(self.telescope.telInfo()) # extra telescope info not captured by MaxIm DL

        newHeader.update(self.getInstStatus())   # instrument info not captured by MaxIm DL

        if not self.site is None:
            newHeader.update(self.site.siteTelemetry()) # observing site roof and weather station info

        # filter numerical position info (MaxIm only records the filter ID)            
        
        if light:
            newHeader["FILTPOS"] = filtNum
            
        # define the timeout for exposure completion to be the larger of self.minExpTimeout or 1.5*expTime

        timeout = max(self.minExpTimeout,1.5*expTime)
               
        if light:
            self.ccd.Expose(expTime,light,filtNum) # light=1 image requires filter selection
        else:
            self.ccd.Expose(expTime,light)         # light=0 image omit filter

        # exposure timer
        
        t0 = time.time() # starting time
        acqTime = 0.0
        
        # Loop, watching the ImageReady and CameraStatus conditions
        
        while(not self.ccd.ImageReady and acqTime < timeout):
            camStatus = self.ccd.CameraStatus
            # only log at when the camera status changes
            if lastState is not camStatus:
                logger.info(f"{self.statusCodes[camStatus]} [CamStatus={camStatus}]")
                lastState = camStatus
                acqTime = time.time() - t0
            time.sleep(self.queryCadence) # don't query camera status more frequently than queryCadence

        # did we end successfully (ImageReady) or timeout?

        if acqTime > timeout:
            if not self.ccd.ImageReady:
                msg = f"Exposure timed out after {timeout:.1f} seconds"
                logger.error(msg)
                raise RuntimeError(msg)
            else:
                logger.warning(f"Exposure timed out after {timeout:.1f} seconds")              
                
        if light:
            logger.info(f"Exposure done: {expTime:.1f} sec {self.filterList[filtNum]} image ready in buffer")
        else:
            if expTime > 0:
                logger.info(f"Exposure done: {expTime:.1f} sec dark image ready in buffer")
            else:
                logger.info("Exposure done: bias image ready in buffer")

        # data ready to save, export as FITS
        
        if saveFile:
            outFITS = self.getNextFile(imgType)
            
            # update the FITS headers with exposure info not captured by MaxIm

            self.updateFITSHeader(newHeader)

            # write the FITS file

            try:
                self.ccd.SaveImage(outFITS)
            except Exception as exp:
                msg = f"Attempt to write FITS file {outFITS} failed: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)
                
        else:
            logger.info("FITS image acquired but not saved as directed")
            

    def science(self,*args):
        """
        Acquire science images using an obsDef array

        Parameters
        ----------
        obsDef : list
            observation definition list

        or
        
        expTime : float
            exposure time in seconds
        filtNum : integer
            filter number (0..numFilt-1) of the filter to use.
        nimgs : int, optional
            number of images to acquire. The default is 1.        
        

        Raises
        ------
        ValueError
            if invalid observation parameters are encountered.
        RuntimeError
            if problems occur during image acquisition.

        Returns
        -------
        None.

        Description
        -----------
        Acquires one or more science images through a single filter
        Arguments are either an `obsDef` array format:
        
            [filtID,expTime,nimgs] : [string,float,int]
        
        or individual arguments: `expTime`, `filtNum`, and `nimgs` in
        the same argument order as the `flat()` method.
        
        This method, unlike the calibration methods `bias()`, `flat()`,
        and `dark()` require that oroject-specific information has
        been defined either with the `projectInfo()` method, or by
        setting `projInfo` property to ensure the correct project
        ownership information is in the image FITS headers.
        
        Uses the acquire() method to do the work.  Science are named
        "sciCCYYMMDD.####.fits" in the current data directory

        See Also
        --------
        bias, dark, flat, acquire, projectInfo
        """
        
        # command line arguments, 1, 2, or 3:
            
        if len(args) == 1:
            obsDef = args[0]
            if len(obsDef) == 3:
                filtID = obsDef[0]
                try:
                    filtNum = self.filterNum(filtID)
                except Exception as exp:
                    self.msg = exp
                    raise ValueError(self.msg)                   
                expTime = obsDef[1]
                nimgs = obsDef[2]
            else:
                self.msg = f"invalid argument {args[0]}, obsDef must be a list of length 3"
                logger.error(self.msg)
                raise ValueError(self.msg)

        # for 3 args, order like flat(): (expTime,filtNum,nimgs)

        elif len(args) == 3:
            expTime = args[0]
            filtNum = args[1]
            nimgs = args[2]

        # for 2 args, order like flat(): (expTime,filtNum) and default nimgs=1

        elif len(args) == 2:
            expTime = args[0]
            filtNum = args[1]
            nimgs = 1

        else:
            self.msg = f"invalid arguments: {args} - see documentation"
            logger.error(self.msg)
            raise ValueError(self.msg)
            
        # validation
        
        if expTime < 0 or expTime > self.maxExpTime:
            msg = f"Invalid exposure time {expTime:.2f} sec, must be 0..{self.maxExpTime}"
            logger.error(f"science(): {msg}")
            raise ValueError(msg)
        
        if filtNum < 0 or filtNum > self.numFilt - 1:
            msg = f"Invalid filter {filtNum}, must be 0..{self.numFilt-1}"
            logger.error(f"science(): {msg}")
            raise ValueError(msg)
            
        filtID = self.filterList[filtNum]

        # acquire nimgs science images of exptime each through filter filtNum
        
        if nimgs > 1:
            logger.info(f"Acquiring {nimgs} {expTime:.1f} sec {filtID} science images")
        else:
            logger.info(f"Acquiring a {expTime:.1f} sec {filtID} science image")
            
        for i in range(nimgs):
            if nimgs > 1:
                logger.info(f"Acquiring {filtID} science image {i+1} of {nimgs}")
            try:
                self.acquire("sci",expTime,filtNum)
            except Exception as exp:
                if nimgs > 1:
                    msg = f"Could not acquire {filtID} science image {i+1} of {nimgs}: {exp}"
                else:
                    msg = f"Could not acquire {filtID} science image"
                logger.exception(msg)
                raise RuntimeError(f"{msg} - science images aborted")
        
        if nimgs > 1:
            logger.info(f"Done: acquired {nimgs} {expTime:.1f} sec {filtID} science images")
        else:
            logger.info(f"Done: acquired a {expTime:.1f} sec {filtID} science image")
        

    def bias(self,nimgs=1):
        """
        Acquire bias calibration images

        Parameters
        ----------
        nimgs : int, optional
            number of bias images to acquire. The default is 1.

        Raises
        ------
        RuntimeError
            Raised if any problems acquiring images.

        Returns
        -------
        None.
        
        Description
        -----------
        Acquires one or more bias calibration images.  Because
        bias images do not require telescope tracking, guiding,
        or a filter we minimize overhead by acquiring multiple
        biases in one command rather than looping at a higher level.
        
        Uses the acquire() method to do the work.  Bias images are named
        "biasCCYYMMDD.####.fits" in the current data directory.

        See Also
        --------
        acquire, dark, and flat
        """
        
        # calibration program info for the FITS headers
        
        self.projInfo.update(self.calProgram)
        self.projInfo["OBJECT"] = "Bias"
        
        # acquire nimgs bias images
        
        if nimgs > 1:
            logger.info(f"Acquiring {nimgs} bias images")
        else:
            logger.info("Acquiring a bias image")
            
        for i in range(nimgs):
            if nimgs > 1:
                logger.info(f"Acquiring bias image {i+1} of {nimgs}")
            try:
                self.acquire("bias")
            except Exception as exp:
                if nimgs > 1:
                    msg = f"Could not acquire bias {i+1} of {nimgs}: {exp}"
                else:
                    msg = "Could not acquire bias image"
                logger.exception(msg)
                raise RuntimeError(f"{msg} - biases aborted")
                        
        if nimgs > 1:
            logger.info(f"Done: acquired {nimgs} bias images")
        else:
            logger.info("Done: acquired bias image")
        
        
    def dark(self,expTime,nimgs=1):
        """
        Acquire dark calibration images

        Parameters
        ----------
        expTime : float
            exposure time in seconds.
        nimgs : int, optional
            number of dark images to acquire. The default is 1.

        Raises
        ------
        ValueError
            Raised if invalid parameters given
        RuntimeError
            Raised if any problems acquiring images.

        Returns
        -------
        None.
        
        Description
        -----------
        Acquires one or more dark images.  Because darks do not
        require telescope tracking, guiding, or a filter selection,
        we minimize overhead by acquiring multiple darks in one command
        rather than looping at a higher level.
        
        Uses the acquire() method to do the work.  Dark images are named
        "darkCCYYMMDD.####.fits" in the current data directory

        See Also
        --------
        bias, flat, acquire
        """
        # validation
        
        if expTime < 0 or expTime > self.maxExpTime:
            msg = f"Invalid exposure time {expTime:.2f} sec, must be 0..{self.maxExpTime}"
            logger.error(f"dark(): {msg}")
            raise ValueError(msg)
        
        # calibration program info for the FITS headers
        
        self.projInfo.update(self.calProgram)
        self.projInfo["OBJECT"] = f"{expTime:.1f}s Dark"

        # acquire nimgs dark images of exptime each
        
        if nimgs > 1:
            logger.info(f"Acquiring {nimgs} {expTime:.1f} sec dark images")
        else:
            logger.info("Acquiring a {expTime:.1f} sec dark image")
            
        for i in range(nimgs):
            if nimgs > 1:
                logger.info(f"Acquiring dark image {i+1} of {nimgs}")
            try:
                self.acquire("dark",expTime)
            except Exception as exp:
                if nimgs > 1:
                    msg = f"Could not acquire dark image {i+1} of {nimgs}: {exp}"
                else:
                    msg = "Could not acquire dark image"
                logger.exception(msg)
                raise RuntimeError(f"{msg} - dark images aborted")
        
        if nimgs > 1:
            logger.info(f"Done: acquired {nimgs} {expTime:.1f} sec dark images")
        else:
            logger.info("Done: acquired a {expTime:.1f} sec dark image")
        
    
    def flat(self,expTime,filtNum,nimgs=1):
        """
        Acquire flat field images

        Parameters
        ----------
        expTime : float
            exposure time in sections.
        filtNum : integer
            filter number (0..numFilt-1) of the filter to use.
        nimgs : int, optional
            number of images to acquire. The default is 1.

        Raises
        ------
        ValueError
            raised if invalid parameters are given.
        RuntimeError
            raised if there are problems with data acquisition

        Returns
        -------
        None.

        Description
        -----------
        Acquires one or more flat field images.  Because flats do not
        require telescope tracking or guiding, we minimize overhead by 
        acquiring multiple flats in one command rather than looping at 
        a higher level.
        
        `filtNum` must be a number between 0 and numFilt-1.  The
        routine will extact the filterID string to use for object names
        and log entries.
        
        Uses the acquire() method to do the work.  Flat field images are named
        "flatCCYYMMDD.####.fits" in the current data directory

        See Also
        --------
        bias, dark, acquire
        """
        
        # validation
        
        if expTime < 0 or expTime > self.maxExpTime:
            msg = f"Invalid exposure time {expTime:.2f} sec, must be 0..{self.maxExpTime}"
            logger.error(f"flat(): {msg}")
            raise ValueError(msg)
        
        if filtNum < 0 or filtNum > self.numFilt - 1:
            msg = "Invalid filter {filtNum}, must be 0..{self.numFilt-1}"
            logger.error(f"flat(): {msg}")
            raise ValueError(msg)
            
        filtID = self.filterList[filtNum]
        
        # calibration program info for the FITS headers
        
        self.projInfo.update(self.calProgram)
        self.projInfo["OBJECT"] = f"{filtID} Flat Field"

        # acquire nimgs flat field images of exptime each through filter filtNum
        
        if nimgs > 1:
            logger.info(f"Acquiring {nimgs} {expTime:.1f} sec {filtID} flat fields images")
        else:
            logger.info("Acquiring a {expTime:.1f} sec {filtID} flat field image")
            
        for i in range(nimgs):
            if nimgs > 1:
                logger.info(f"Acquiring {filtID} flat image {i+1} of {nimgs}")
            try:
                self.acquire("flat",expTime,filtNum)
            except Exception as exp:
                if nimgs > 1:
                    msg = f"Could not acquire {filtID} flat field image {i+1} of {nimgs}: {exp}"
                else:
                    msg = "Could not acquire {filtID} flat field image"
                logger.exception(msg)
                raise RuntimeError(f"{msg} - flat field images aborted")
        
        if nimgs > 1:
            logger.info(f"Done: acquired {nimgs} {expTime:.1f} sec {filtID} flat field images")
        else:
            logger.info("Done: acquired a {expTime:.1f} sec {filtID} flat field image")
        
        
    #------------------------------------
    #
    # Guide Telescope Autoguider functions
    #
    # Code to operate the CMOS guide camera
    # on the co-axial guide telescope.
    #
    
    def guideMove(self,dTx,dTy):
        """
        Offset the telescope for guide corrections

        Parameters
        ----------
        dTx : float
            duration of guider slew in X in seconds, +=positive X, -=negative X 
        dTy : float
            duration of guider slew in Y in seconds, +=positive Y, -=negative Y
            
        Raises
        ------
        RuntimeError
            if errors sending guider offsets

        Returns
        -------
        None.

        Description
        -----------
        The Maxim.CCDCamera.GuiderMove() method takes 2 arguments: a direction
        and a duration in seconds.  Directions are (0=+X,1=-X,2=+Y,3=-Y).
        
        This function implements 2-axis guider moves for by exposing the 
        GuiderMove() method through a Camera class instance.  For example,
        to execute guide moves computed by the DEMONEXT science guiding mode.
        
        See: https://cdn.diffractionlimited.com/help/maximdl/MaxIm-DL.htm#t=GuiderMove.htm
        """
        logger.info(f"Executing guider move dT_x={dTx:.3f} sec, dT_y={dTy:.3f} sec")
        
        # Info to build the command syntax for MaxIm.CCDCamera.GuiderMove()
        # we extract direction and sign
        
        if dTx >= 0:
            dirx = 0
            sx = "+"
        else:
            dirx = 1
            sx = "-"
            
        if dTy >= 0:
            diry = 2
            sy = "+"
        else:
            diry = 3
            sy = "-"
            
        # motion time delays, requested slew time + 1 seccond
        
        dxDelay = int(abs(dTx)) + 1 # seconds
        dyDelay = int(abs(dTy)) + 1 # seconds
        
        # execute the moves if non-zero, x then y directions
        
        if abs(dTx) > 0:
            try:
                logger.info(f"Executing {abs(dTx):.3f} second duration guide move in {sx}X")
                self.ccd.GuiderMove(dirx,abs(dTx))
                time.sleep(dxDelay)
            except Exception as exp:
                msg = f"Cannot execute guide move of {abs(dTx):.3f} seconds in {sx}X: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)
        
        if abs(dTy) > 0:
            try:
                logger.info(f"Executing {abs(dTy):.3f} second duration guide move in {sy}Y")
                self.ccd.GuiderMove(diry,abs(dTy))
                time.sleep(dyDelay)
            except Exception as exp:
                msg = f"Cannot execute guide move of {abs(dTy):.3f} seconds in {sy}Y: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)
                

    def findGuideStar(self):
        """
        Find a suitable guide star and guider exposure time

        Raises
        ------
        RuntimeError
            if errors communicating with the guide camera via MaxIm DL

        Returns
        -------
        goodStar : boolean
            True if a good guidestar has been found, false if no guide star found
        expTime : float
            minimum exposure time that results in a good guide star.

        Description
        -----------
        Uses the MaxIm DL autoguider algorithm to identify a suitable guide
        star and exposure time to use for autoguiding.
        
        See Also
        --------
        guiderCalib, guidingOn
        """
        
        # setup guider auto star selection
        
        try:
            self.ccd.GuiderAutoSelectStar = False
            self.ccd.GuiderSetStarPosition(1,1)
            starX = self.ccd.GuiderXStarPosition
            starY = self.ccd.GuiderYStarPosition
        except Exception as exp:
            msg = f"Cannot setup guide camera star finder: {exp}"
            logger.error(msg)
            self.msg = f"ERROR: {msg}"
            return False, 0.0
        
        # Try to find a good guide star using a guider camera exposure time ramp
        # from short to long integrations (self.guiderExpTimes list)
        
        goodStar = False
        expTime = self.guiderExpTimes[0]
    
        # instruct the autoguider to auto-select a guide star 
        
        self.ccd.GuiderAutoSelectStar = True
       
        # iterate over exposure times to find one that works
        
        iExp = 0
        while not goodStar and iExp < len(self.guiderExpTimes):
            expTime = self.guiderExpTimes[iExp]
            self.ccd.GuiderExpose(expTime)
            logger.info(f"Starting guide camera star finding exposure {expTime:.1f} sec")
            time.sleep(self.guideCadence)
            while self.ccd.GuiderRunning:
                time.sleep(self.guideCadence)
            
            newStarX = self.ccd.GuiderXStarPosition
            newStarY = self.ccd.GuiderYStarPosition
            
            # compare star at new position to the old position
            
            if int(starX) != int(newStarX) or int(starY) != int(newStarY):
                logger.info(f"Found a good guide star at ({newStarX:.2f},{newStarY:.2f})")
                goodStar = True
            else:
                logger.info(f"No good guide star found in {expTime:.1f} sec exposure, iterating")
                iExp += 1
        
        return goodStar, expTime

        
    def guiderCalib(self):
        """
        Calibrate the off-axis autoguider camera

        Raises
        ------
        RuntimeError
            if errors setting up the calibration.

        Returns
        -------
        bool
            True if successful calibration, False if calibration failed.

        Description
        -----------
        Find a good guide star and exposure time, then calibrate the
        autoguider camera to prepare for guiding.  Autoguider calibration
        should only need to be done once per night.
        
        Uses the findGuideStar() method to identify a good guide star
        """
        logger.info("Calibrating the autoguider camera")

        # find a suitable guide star and guiding exposure time

        goodStar, expTime = self.findGuideStar()

        # If we found a good guide star, begin guider calibration.  
        # This should only need to be done once per night.
        
        if goodStar:
            logger.info(f"Starting autoguider calibration, expTime={expTime:.1f} sec")
            self.ccd.GuiderCalibrate(expTime)
            time.sleep(self.guideCadence)
            while self.ccd.GuiderCalState == 1:
                time.sleep(self.guideCadence)
            
            if self.ccd.GuiderCalState == 2:
                logger.info("Guider calibration successful")
                return True
            else:
                msg = "Guider calibration failed"
                logger.error(msg)
                self.msg = f"ERROR: {msg}"
                return False
            
        else:
            logger.error("Cannot find a good guide star, guider calibration aborted")
            return False
        
        
    def guidingOff(self):
        """
        Disable autoguiding

        Raises
        ------
        RuntimeError
            if ASCOM communication with the MaxIm DL autoguider fails.

        Returns
        -------
        None.

        See Also
        --------
        guidingOn, guiderCalib
        """
        try:
            logger.info("Disabling autoguiding")
            self.ccd.GuiderStop
        except Exception as exp:
            msg = f"Cannot disable autoguiding: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
                
    def guidingOn(self):
        """
        Enable autoguiding and start guiding

        Returns
        -------
        boolean
            True if guiding started, False if not guiding.  msg contains
            a message why.

        """        
        # cannot proceed unless the guider is calibrated
        
        if self.ccd.GuiderCalState != 2:
            msg = "Guider has not been calibrated, cannot start guiding"
            logger.error(msg)
            self.msg = f"ERROR: {msg}"
            return False

        # we're ready to start
            
        logger.info("Enabling autoguiding")
        
        self.ccd.GuiderAggressiveness = self.aggressiveness
        
        # find a suitable guide star and guiding exposure time

        goodStar, expTime = self.findGuideStar()

        # If we found a good guide star, begin guiding
        
        try:
            self.ccd.GuiderTrack(expTime)
            logger.info("Started autoguiding with {expTime:.1f} sec exposures")
        except Exception as exp:
            msg = f"Cannot start autoguiding: {exp}"
            logger.error(msg)
            self.msg(f"ERROR: {msg}")
            return False
            
        return self.ccd.GuiderRunning


    def isGuiding(self):
        """
        Is the autoguider running?

        Returns
        -------
        boolean
            True if guider is running, False if guider is idle.

        """    
        return self.ccd.GuiderRunning
    
    
    def acqGuider(self,expTime,save=True):
        """
        Acquire and save a guide camera image

        Parameters
        ----------
        expTime : float
            exposure time in seconds.
        save : boolean, optional
            Save the guide camera image as FITS. The default is True.

        Raises
        ------
        ValueError
            if invaled exposure time is given.
        RuntimeError
            if there are errors operating the guide camera.

        Returns
        -------
        None.

        Description
        -----------
        Acquires a single exposure of `expTime` duration with the guide
        camera and saves the image to disk with a minimal FITS header.
        
        Images have names "gcamCCYYMMDD.####.fits" in the current data directory
        """
        # validate exposure time
        
        if expTime < 0 or expTime > self.maxExpTime:
            msg = f"Invalid expTime {expTime:.2f} sec, must be 0..{self.maxExpTime:.1f} sec"
            logger.exception(msg)
            raise ValueError(msg)
            
        # operation timeout
        
        timeOut = max(self.minExpTimeout,1.5*expTime)
        
        # Start guide exposure
        
        logger.info(f"Starting {expTime:.1f} sec guide camera exposure...")
        
        # get start of exposure telescope pointing info if saving
 
        if save:
            telStart = self.telescope.telFITS()
        
        # start exposure timer
               
        t0 = time.time()
        acqTime = 0.0

        try:
            self.ccd.GuiderExpose(expTime)
        except Exception as exp:
            msg = f"Cannot start guide camera exposure: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
        # watcher loop: GuiderRunning True and not timeout
            
        while (self.ccd.GuiderRunning and acqTime < timeOut):
            time.sleep(self.queryCadence)
            acqTime = time.time() - t0
        
        if (acqTime > timeOut):
            if self.ccd.GuiderRunning:
                msg = f"Guide camera exposure timed out after {timeOut:.1f} sec"
                logger.error(msg)
                raise RuntimeError(msg)
            else:
                logger.warning("Guide camera exposure timed out, but apparently finished")
        
        if save:
            logger.info("Guide camera exposure complete, writing to disk")
        else:
            logger.info("Guide camera exposure complete, not written (save=False)")
    
        # write image to disk in FITS format
        
        if save:
            logger.info("Downloading guide image array from MaxIM")
            try:
                rawImg = np.array(self.ccd.GuiderArray) # retrieve data from MaxIm
            except Exception as exp:
                msg = f"Cannot download image array from MaxIm: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)
            
            # make FITS primary array and header
            
            outFITS = self.getNextFile('gcam')
            
            hdu = fits.PrimaryHDU(data=rawImg)
            hdul = fits.HDUList([hdu])
            hdr = hdul[0].header
            hdr['OBJECT'] = 'Guide Camera'
            hdr['TELESCOP'] = (self.guideScope,'Guide Telescope')
            hdr['INSTRUME'] = (self.guideCam,'Guide Camera')
            hdr['FILTER'] = (self.guideFilter,'Guide Camera Filter')
            hdr['EXPTIME'] = (expTime,'Exposure time [sec]')
            hdr['GCAMTEMP'] = (self.ccd.GuiderTemperature,'Sensor temperature [C]')
            
            # start of exposure telescope pointing info
            
            for key, val in telStart.items():
                hdr[key] = val

            # write FITS file to disk
            
            hdul.writeto(outFITS,overwrite=True)
            logger.info(f"Write guide camera FITS image {outFITS}")
        
