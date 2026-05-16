"""DEMONEXT Focuser interface class

Class to remotely operate the PlaneWave Hedrick Focuser using the 
PWI3 app ASCOM interface.

Author
------
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2025 Jan 3

Modification History
--------------------
    2025 Jan 03 - first version [rwp/osu]
    2025 Jan 06 - changes from live testing [rwp/osu]
    
"""

import os
import time

# Windows Component Object Model (COM) client module

from win32com.client import Dispatch

# pathlib for path handling

from pathlib import Path

# yaml for configuration file parsing

import yaml

# logging

import logging
logger = logging.getLogger("Focuser") 

# Focuser Class

class Focuser:
    """Focuser control class
    
    Operates the PlaneWave Hedrick focuser using the PWI3 app and ASCOM
        
    Methods
    -------
    __init__(cfgFile)
        initialize the Focuser class instance, but do not connect to the PWI3 app.
       
        cfgFile: string
            full name of the YAML runtime configuration file to load.
            default: looks in $HOME for `.demonext/config/demonext.txt`
    connect()
        connect and initialize cameras
    disconnect()
        disconnect the cameras
    getFocInfo()
        get focuser status info in FITS-like dictionary format
    getMirrorTemp()
        read the mirror temperature reported by the focuser in degrees C
    getAmbientTemp()
        read the ambient temperature reported by the focuser in degrees C
    getPos()
        get the current absolute focus position, units: microns
    setPos(focDist)
        set the absolute focus position, units: microns
    stepPos(deltaFoc)
        step the focus position +/-deltaFoc relative to the current position, units: microns
    isMoving()
        is the focuser moving?
    findFocus()
        find the best focus position using the PWI3 AutoFocus system
    
    Attributes
    ----------
    connected : bool
        True if connected to MaxIm DL, false if disconnected
    linked : bool
        True if the focuser is linked
    focPos : float
        last measured focus position in microns
    maxFocus : float
        maximum focus position in microns (default: 32000 microns or runtime config file)
    maxExpTime : float
        maximum autofocus exposure time in seconds (default: 120 sec or runtime config file)
    filterOffset : list of floats
        filter focus offsets for the filters relative to `refFilter` (default: 0 or runtime config file)
    refFilter : integer
        reference filter for `filterOffset` (default: 0 or runtime config file)
    queryCadence : float
        fastest cadence to query the focuser (minimum: 0.1 seconds)
    focusTimeout : float
        focus motion timeout in seconds. 2x full range motion is 120s
    autoFocTimeout : float
        autofocus system timeout in seconds

    """
    
    def __init__(self,*args):
        """
        Constructor for the Focuser class. 

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
        needed to operate the Hedrick focuser and the PlaneWave AutoFocuser
        systems, but does not connect with the PWI3 app. That is done with 
        the connect() method.

        If no runtime configuration file is given, it defaults to a file 
        named demonext.txt in the user .demonext/config/ directory 
        (default expectation).  We load it directly rather than using
        the Config class.

        """
        
        # ASCOM classes

        self.focASCOM = "ASCOM.PWI3.Focuser"
        self.afASCOM = "PlaneWave.AutoFocus"

        # ASCOM class instances
        
        self.focuser  = None # ASCOM Focuser object
        self.autoFoc = None # ASCOM AutoFocus object

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
                
            # focuser configuration info
                
            try:
                self.focConfig = config["focuser"]
            except:
                self.focConfig = None

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

        # Runtime flags
        
        self.connected = False
        self.linked = False
        self.name = ''
        
        # Defaults if no focuser config information. These are based on a combination
        # of focuser specifications and measurements of a PlaneWave Hedrick focuser.

        self.filterOffset = []  # focus offsets by filter
        self.refFilter = 0      # reference filter for filterOffset
        self.refFocus = 0.0     # nominal reference focus position in microns
        self.maxFocus = 33000.  # maximum focus in microns (Hedrick focuser spec)
        self.maxExpTime = 120.  # maximum autofocus exposure time in seconds
        
        # Update from the runtime config file as needed
        
        if self.focConfig:
            if "FilterOffsets" in self.focConfig:
                self.filterOffsets = self.focConfig["FilterOffsets"]
            if "RefFilter" in self.focConfig:
                self.refFilter = self.focConfig['RefFilter']
            if "RefFocus" in self.focConfig:
                self.refFocus = self.focConfig["RefFocus"]
            if "MaxFocus" in self.focConfig:
                self.maxFocus = self.focConfig["MaxFocus"]
            if "MaxExpTime" in self.focConfig:
                self.maxExpTime = self.focConfig["MaxExpTime"]
                
        # time delays for various operations

        self.connectDelay = 2 # seconds
        self.dispatchDelay = 2 # seconds
        self.timeDelay = 1 # seconds
        self.autoFocDelay = 10 # seconds between autofocus steps
        self.queryCadence = 0.1 # seconds - fastest we should emit queries to the focuser

        # AutoFocus parameters
        
        self.mirrorSensor = "Primary.EFA"   # EFA primary mirror temperature sensor
        self.ambientSensor = "Ambient.EFA"  # EFA ambient temperature sensor 
        
        # Useful boolean translation dictionaries

        self.OnOff = {True:"On",False:"Off"}
        self.YesNo = {True:"Yes",False:"No"}

        # operation timeouts

        self.focusTimeout = 120.0   # seconds (~2x full range in/out)
        self.autoFocTimeout = 600.0 # seconds
        
        # other stuff

        self.bestFocus = self.refFocus  # nominal best focus to start
        
        # internal messages

        self.msg = ""


    # Methods

    #--------------------------------
    #
    # app startup and ASCOM methods
    #

    def connect(self):
        """
        Connect to PWI3 and PlaneWave AutoFocus apps

        Raises
        ------
        RuntimeError
            Raised if it cannot connect with ASCOM services or
            gets errors on setting up the focuser.

        Returns
        -------
        None.
        
        Description
        -----------
        Creates Windows Common Object Module (COM) client ASCOM interface
        instances for communicating with the PWI3 application that controls 
        the Hedrick focuser and its associated AutoFocus utility.
        
        The PWI3 app will be launched if not already running and put in
        the background (unless it is configured to start in the foreground).
        Wait dispatchDelay to ensure it is running before other operations to
        avoid race conditions with startup.
 
        In addition to connecting we veriyf the link state of the focuser hardware
        and ask the PWI3 app for the name of the focuser.
        
        See Also
        --------
        disconnect
        """

        # instantiate PWI3 Focuser application COM client
        
        try:
            self.focuser = Dispatch(self.focASCOM)
            time.sleep(self.dispatchDelay)
            self.connected = True
            logger.info("Started PWI3 Focuser app connection")
        except Exception as exp:
            msg = f"Cannot start {self.focASCOM} COM client: {exp}"
            logger.exception(msg)
            self.focuser = None
            self.connected = False
            self.linked = False
            raise RuntimeError(msg)

        # connect to the PWI3 app
        
        try:
            self.focuser.Connected = True
            logger.info("Connected to the PWI3 focuser app")
        except Exception as exp:
            msg = f"Cannot connect to the PWI3 app: {exp}"
            logger.exception(msg)
            self.focuser = None
            self.connected = False
            self.linked = False
            raise RuntimeError(msg)
            
        time.sleep(self.connectDelay)
        
        # Ask PWI3 to verify link the Hedrick focuser - would return False if
        # the focuser is powered off or disconnected (USB to EFA or EFA to focuser)

        try:
            self.linked = self.focuser.Link
        except Exception as exp:
            msg = f"Cannot verify PWI3 link to the Hedrick Focuser: {exp}"
            logger.exception(msg)
            self.linked = False
            raise RuntimeError(msg)

        if self.linked:
            logger.info("PWI3 linked to the Hedrick Focuser")
        else:
            msg = "PWI3 not linked to the Hedrick Focuser at startup - check power or connectors"
            logger.error(msg)
            raise RuntimeError(msg)
            
        # instantiate an AutoFocus COM client

        try:
            self.autoFoc = Dispatch(self.afASCOM)
            time.sleep(self.dispatchDelay)
            logger.info("PWI3 AutoFocus connection established")
        except Exception as exp:
            msg = f"Cannot connect to the {self.afASCOM} COM client: {exp}"
            logger.exception(msg)
            self.autoFoc = None
            raise RuntimeError(msg)

        # Get focuser name and current position
        
        self.connected = True
        self.linked = True
        self.name = self.focuser.Description
        self.focPos = self.focuser.Position
        self.ambientTemp = self.autoFoc.GetTemperatureByName(self.ambientSensor)
        self.mirrorTemp = self.autoFoc.GetTemperatureByName(self.mirrorSensor)
        
        self.msg = f"{self.name} connected, starting position {self.focPos} microns, mirror temp {self.mirrorTemp:.1f}C, ambient {self.ambientTemp:.1f}C"
        logger.info(self.msg)
        
        # all done!
        
        logger.info("Focuser Startup Complete")


    def disconnect(self):
        """
        Disconnect from the Focuser and remove the ASCOM object instances.

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

        if self.focuser.Connected:
            logger.info(f"Disconnecting the {self.name}")
            try:
                self.focuser.Connected = False
                time.sleep(self.connectDelay)
            except Exception as exp:
                msg = f"Cannot disconnect the {self.name}: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)

        # release the ASCOM classes
        
        self.focuser = None
        self.autoFoc = None
        self.connected = False

        logger.info(f"{self.name} disconnection complete")
        self.name = ""
        

    #------------------------------------
    #
    # Focuser info methods
    #
    
    def getFocInfo(self):
        """
        Get focuser status information as FITS-style keywords

        Returns
        -------
        dict
            focInfo dictionary with focuser information in FITS-like format.

        Description
        -----------
        Queries the focuser and returns the current status as a set of
        FITS-like keyword/value pairs:
         * FOCNAME: string - focuser unit name    
         * FOCLINK: string - is focuser linked to PWI3? True=linked, False=not linked
         * FOCUSPOS: float - current absolute position in microns, 0 = closest to secondary mirror
         * FOCMOVE: boolean - is focuser moving? True=moving, False=idle
         * AMB_TEMP: float - telescope ambient air temperature in degrees C
         * MIR_TEMP: float - telescope primary mirror temperature in degrees C
         * FOCSTEP: float - focuser step size in microns per step
                
        """
        
        self.focInfo = {}
        
        self.focInfo['FOCNAME'] = self.focuser.Description 
        self.focInfo['FOCLINK'] = self.focuser.Link
        self.focInfo['FOCUSPOS'] = self.focuser.Position
        self.focInfo['FOCMOVE'] = self.focuser.IsMoving
        self.focInfo['AMB_TEMP'] = self.autoFoc.GetTemperatureByName(self.ambientSensor)
        self.focInfo['MIR_TEMP'] = self.autoFoc.GetTemperatureByName(self.mirrorSensor)
        self.focInfo['FOCSTEP'] = self.focuser.StepSize
        
        return self.focInfo        


    def getTemps(self):
        """
        Read the focuser's temperature sensors

        Raises
        ------
        RuntimeError
            if the temperature sensors cannot be read

        Returns
        -------
        mirrorTemp : float
            Primary mirror temperature in degrees C
        ambientTemp : float
            Ambient air temperature in degrees C

        Note
        ----
        The PlaneWave focuser's electronics box (the EFA), connects to
        primary mirror and ambient air temperature sensors on the
        telescope.  This method reads both sensors, which are exposed
        to the AutoFocuser ASCOM class, and returns values in degrees C.
        
        """
        try:
            self.mirrorTemp = self.autoFoc.GetTemperatureByName(self.mirrorSensor)
            self.ambientTemp = self.autoFoc.GetTemperatureByName(self.ambientSensor)
            logger.info(f"Telescope primary mirror temperature {self.mirrorTemp:.1f}C  Ambient {self.ambientTemp:.1f}C")
            return self.mirrorTemp, self.ambientTemp
        except Exception as exp:
            msg = f"Cannot read telescope temperature sensors: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)


    def getAmbientTemp(self):
        """
        Read the telescope ambient air temperature sensor

        Raises
        ------
        RuntimeError
            if errors reading the focuser temperature sensors.

        Returns
        -------
        float
            ambient air temperature in degrees C.

        See Also
        --------
        getTemps, getMirrorTemp
        """
        try:
            self.ambientTemp = self.autoFoc.GetTemperatureByName(self.ambientSensor)
            logger.info(f"Telescope Ambient Temperature {self.ambientTemp:.1f}C")
            return self.ambientTemp
        except Exception as exp:
            msg = f"Cannot read telescope ambient temperature sensor: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        

    def getMirrorTemp(self):
        """
        Read the telescope primary mirror temperature sensor

        Raises
        ------
        RuntimeError
            if errors reading the focuser temperature sensors.

        Returns
        -------
        float
            telescope primary mirror temperature in degrees C.

        See Also
        --------
        getTemps, getAmbientTemp
        """
        try:
            self.mirrorTemp = self.autoFoc.GetTemperatureByName(self.mirrorSensor)
            logger.info(f"Telescope Primary Mirror Temperature {self.ambientTemp:.1f}C")
            return self.mirrorTemp
        except Exception as exp:
            msg = f"Cannot read telescope primary mirror temperature sensor: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

    #------------------------------------
    #
    # Focus position set/get methods
    #

    def getPos(self):
        """
        Return the current focus absolute position
        
        Raises
        ------
        RuntimeError
            Raised if the focuser position query fails.

        Returns
        -------
        float
            current focuser absolute position in microns
            
        See Also
        --------
        setPos, stepPos, getFocInfo
        """
        try:
            focPos = self.focuser.Position
        except Exception as exp:
            msg = f"Cannot query current focuser position: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        self.focPos = focPos
        return self.focPos
    
    
    def setPos(self,reqPos):
        """
        Move the focuser to the requested position
        
        Parameters
        ----------
        reqPos : float
            requested focuser absolute position in microns
            range: 0..maxFocus
            
        Raises
        ------
        ValueError
            Raised if reqPos is outside the range 0..maxFocus
        RuntimeError
            Raised on errors setting or querying the focuser.

        Returns
        -------
        None.

        Description
        -----------
        Moves the focuser to the requested absolute position in microns.
        Watches the IsMoving state flag to determine when motion is
        complete or the motion time exceeds the timeout (focusTimeout).    
        
        See Also
        --------
        getPos, stepPos
        """
        # validate  the requested focus position
        
        if reqPos < 0 or reqPos > self.maxFocus:
            msg = f"Requested focus position {reqPos} out of range, must be 0..{self.maxFocus}"
            logger.exception(msg)
            raise ValueError(msg)
        
        # do we need to move?
        
        if reqPos == self.focuser.Position:
            return
        
        # Perform the motion - watch the IsMoving state flag to
        # see when motion completes
        
        logger.info(f"Focuser starting at {self.focuser.Position} microns, moving to {reqPos} microns")

        t0 = time.time()
        try:
            self.focuser.Move(reqPos)
        except Exception as exp:
            msg = f"Cannot start focuser move: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
        # start the motion timer
        
        t0 = time.time()
        focTime = 0.0
        
        while(self.focuser.IsMoving and focTime < self.focusTimeout):
            time.sleep(self.queryCadence)
            focTime = time.time() - t0

        if focTime > self.focusTimeout:
            logger.warning(f"Focus motion timed out after {self.focusTimeout:.0f} seconds")
            logger.warning(f"      current focus position: {self.focuser.Position} microns")
        else:
            logger.info(f"Done: Focuser at position {self.focuser.Position} microns")
            self.focPos = self.focuser.Position        
        
    
    def stepPos(self,deltaFoc):
        """
        Step the focus relative to the current focus position

        Parameters
        ----------
        deltaFoc : float
            Focus step in microns, + away from the secondary mirror, - towards

        Raises
        ------
        ValueError
            if the requested focus step would exceed the focuser range.
        RuntimeError
            if the requested focus step is valid but could not be executed.

        Returns
        -------
        None.

        Description
        -----------
        The focuser is moved in absolute units, this function provides a way
        to change the focus in relative deltaFocus steps.  The requested
        step is validated against the focuser limits.
        
        Uses the `setPos` method to execute the move.
        
        See Also
        --------
        setPos, getPos
        """
        # get the current focus position
        
        curPos = self.focuser.Position
        
        # compute the new relative position
        
        newPos = curPos + deltaFoc
        
        # validate against the absolute limits
        
        if newPos < 0:
            msg = f"Focus step {deltaFoc:.0f} microns is past the zero (home) focus position"
            logger.error(msg)
            raise ValueError(msg)
        elif newPos > self.maxFocus:
            msg = f"Focus step {deltaFoc:.0f} microns would move beyond maximum focus {self.maxFocus} microns"
            logger.error(msg)
            raise ValueError(msg)
            
        # we have a valid move, do it
        
        logger.info(f"Stepping focus by {deltaFoc:.0f} microns from {curPos:.0f} microns")
        try:
            self.setPos(newPos)
        except Exception as exp:
            msg = f"Cannot execute requested focus step: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
            
        # all done
        
        self.focPos = self.focuser.Position
        logger.info(f"Done: focus step {deltaFoc:.0f} microns complete, new focus {self.focPos:.0f}microns")
        
    
    def isMoving(self):
        """
        Is the focuser moving?

        Raises
        ------
        RuntimeError
            if it cannot read the focuser IsMoving status flag.

        Returns
        -------
        boolean
            True if the focuser is moving, False if idle.

        """
        try:
            return self.focuser.IsMoving
        except Exception as exp:
            msg = f"Cannot read focuser IsMoving state: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
                       
    #------------------------------------
    #
    # AutoFocus methods
    #
    #

    def findFocus(self,expTime):
        """
        Use the PlaneWave AutoFocus utility to find best focus

        Parameters
        ----------
        expTime : float
            Focus image exposure time in seconds.

        Raises
        ------
        ValueError
            if an invalid exposure time given (must be >0 and not exceed maxExpTime).
        RuntimeError
            if any errors returned by AutoFocus

        Returns
        -------
        float
            best focus position in microns.  Also in the `bestFocus` property.

        Runs the PlaneWave PWI3 AutoFocus utility and computes the best focus
        for the current filter.  Select the filter using the setFilter function
        in the active demonext Camera class instance.
        """
        # validate the focus image exposure time

        if expTime < 0 or expTime > self.maxExpTime:
            msg = f"Focus exposure time {expTime:.1f} sec invalid, must be 1..{self.maxExpTime:0f} seconds"
            logger.error(msg)
            raise ValueError(msg)

        # Set the autofocus exposure time and start autofocus

        logger.info(f"Starting AutoFocus run with exposure time {expTime:.1f} seconds")
        
        try:
            self.autoFoc.ExposureLengthSeconds = expTime
            self.autoFoc.StartAutoFocus
        except Exception as exp:
            msg = f"Cannot start AutoFocus: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # start the autofocus timer

        t0 = time.time()
        focTime = 0.0

        # Watch the IsAutoFocusRunning flag or timeout

        while (self.autoFoc.IsAutoFocusRunning and focTime < self.autoFocTimeout):
            time.sleep(self.autoFocDelay)
            focTime = time.time() - t0

        # Done, did we finish or timeout?

        if focTime > self.autoFocTimeout:
            self.autoFoc.StopAutoFocus
            msg = "AutoFocus timed out, stopping"
            logger.error(msg)
            raise RuntimeError(msg)

        # did AutoFoc find best focus?
        
        if self.autoFoc.Success:
            self.bestFocus = self.autoFoc.BestPosition
            logger.info(f"AutoFocus found best focus at {self.bestFocus:.0f} microns")
            return self.bestFocus

        else:
            msg = "AutoFocus failed to find best focus"
            logger.error(msg)
            raise RuntimeError(msg)

        
        
