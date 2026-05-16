"""DEMONEXT Telescope Control System interface class

Class to remotely operate the DEMONEXT telescope mount through
the PlaneWave STI application using ASCOM.


Author:
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2024 Dec 19

Modification History:
    2024 Dec 19 - first version [rwp/osu]
    2024 Dec 20 - debugging with live telescope [rwp/osu]
    2024 Dec 27 - added slewToRADec() and validRADec() [rwp/osu]
    2024 Dec 28 - cleaned up, added validAltAz(), astropy functions [rwp/osu]
    2024 Dec 30 - coordinate functions, debugged w/live telescope [rwp/osu]
    2024 Dec 31 - minor bug patches with spyder [rwp/osu]
    2024 Jan 01 - bug fixes during live testing with Camera class [rwp/osu]
    2025 Jun 04 - added timezone to default site info [rwp/osu]
    
"""

import os
import time
import math

# Windows Component Object Model (COM) client module

from win32com.client import Dispatch

# pathlib for path handling

from pathlib import Path

# yaml for configuration file parsing

import yaml

# logging

import logging
logger = logging.getLogger("Telescope") 

# astropy units, coordinates, and times

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.coordinates import Angle
from astropy.coordinates import TETE
from astropy.time import Time

# Telescope Class

class Telescope:
    """Telescope interface class

    Operates the telescope mount controller connected through
    the PlaneWave STI application

    Methods
    -------
    __init__(cfgFile)
        initialize the Telescope class instance, but do not connect to the STI app.
       
        cfgFile: string
            full name of the YAML runtime configuration file to load.
            default: looks in $HOME for `.demonext/config/demonext.txt`
    connect()
        connect and initialize the telescope interface
    disconnect()
        disconnect from the telescope
    position()
        query the telescope for position info
    telInfo()
        return telescope info for FITS headers not captured by MaxIm DL
    telFITS()
        return all telescope info in FITS format
    ha()
        compute the hour angle position of the telescope
    secz()
        compute the secant of the zenth distance of the telescope
    isHome()
        is the telescope at the encoder home position?
    isParked()
        is the telescope at the parked position?
    isTracking()
        is the telescope tracking at the sidereal rate?
    isSlewing()
        is the telescope slewing between positions?
    tracking(onoff)
        turn sidereal tracking on or off
    home()
        home the telescope encoders
    park()
        park the telescope and turn off tracking
    slewToAltAz(alt,az)
        slew the telescope to an Alt/Az position
    slewToRADec(appRA,appDec)
        slew the telescope to apparent RA/Dec coordinates
    validRADec(RA,Dec)
        validate apparent RA/Dec coordinates against the telescope pointing limits
    validAltAz(alt,az)
        validate Alt/Az coordinates against the telescope pointing limits
    precess(RAJ2000,DecJ2000)
        precess J2000 RA/Dec coordinates to apparent RA/Dec coordinates now
    dec2sex(decAng,precision=2,sign=False)
        convert a decimal angle to a sexigesimal string to the given precision
    sex2dec(sexStr,precision=8)
        convert a sexigesimal string to a decimal number to the given precision

    Attributes
    ----------
    connected : bool
        True if connected to the mount controller, False if disconnected
    minAlt : float
        minimum altitude for the telescope in degrees, default: 5 degrees
    minHA : float
        minimum hour angle for the telescope in hours, default: -11 hours (east of meridian)
    maxHA : float
        maximum hour angle for the telescope in hours, default: +11 hours (west of meridian)
    parkAlt: float
        altitude of the parked position in degrees, default: 5 degrees
    parkAz : float
        azimuth of the parked position in degrees, default: 180 degrees (HA=0)
    minDec : float
        minimum declination in degrees, default: (latitude-90) + minAlt
    telName : string
        name of the telescope returned by the STI application
    msg : string
        internal message string

    """
    
    def __init__(self,*args):
        """
        Initialize the Telescope class

        Parameters
        ----------
        *args :
            cfgFile : string
                Name and path of a YAML runtime configuration file with the
                telescope controller configuration.
                
        Raises
        ------
        RuntimeError
            Raised if errors reading the configuration file .

        Returns
        -------
        None.

        Description
        -----------
        The constructor initializes all data structures and properties
        needed to operate the telescope with the PlaneWave STI app.
        
        This initializes all the information we need but does not
        connect to the STI app until you use the connect() method.
        
        If no runtime configuration file is given, it defaults to a file 
        named demonext.txt in the user .demonext/config/ directory 
        (default expectation).  We load it directly rather than using
        the Config class.

        """
        
        # ASCOM Telescope class

        self.ASCOM = "SiTech.Telescope"

        self.tel = None # ASCOM telescope object, self.tel = Dispatch(self.ASCOM)
        
        # default site is Sierra Remote Observatories
        
        self.siteInfo = {'OBSERVAT':'DEMONEXT Reboot',
                         'SITENAME':'Sierra Remote Observatories',
                         'SITE_LON':-119.41293,
                         'SITE_LAT':37.07031,
                         'SITE_EL':1405.0,
                         'SITE_TZ':'US/Pacific'}

        # default telescope park position - overload with the telescope config file

        self.parkAz = 180.0
        self.parkAlt = 5.0

        # default minimum "safe" altitude and HA range - overload with the telescope config file

        self.minAlt = 5.0  # degrees
        self.minHA = -11.0 # degrees
        self.maxHA = 11.0  # degrees
        
        # Argument options from nothing, a config file, or individual keywords
        
        if len(args) > 0:
            cfgFile = args[0]
        
        else:  # default config file
            cfgFile = str(Path.home() / ".demonext/config/demonext.txt")

        # open the configuration file and get the info we need for the telescope
        
        if cfgFile is not None:
            with open(cfgFile,"r") as stream:
                try:
                    config = yaml.safe_load(stream)
                except yaml.YAMLError as exp:
                    msg = f"Cannot open runtime configuration file {cfgFile}: {exp}"
                    logger.exception(msg)
                    raise RuntimeError(msg)

                try:
                    self.siteInfo = config["site"]
                    self.siteLat = self.siteInfo["SITE_LAT"]
                    self.siteLon = self.siteInfo["SITE_LON"]
                    self.siteElev = self.siteInfo["SITE_EL"]
                    self.siteTZ = self.siteInfo["SITE_TZ"]
                except:
                    self.siteLat = self.siteInfo["SITE_LAT"]
                    self.siteLon = self.siteInfo["SITE_LON"]
                    self.siteElev = self.siteInfo["SITE_EL"]
                    self.siteTZ = self.siteInfo["SITE_TZ"]
                    
                stream.close()
            
            else:
                msg = f"Runtime configuration file {cfgFile} does not exist"
                logger.exception(msg)
                raise RuntimeError(msg)
        
        # Runtime flags

        self.stiRunning = False
        self.connected = False
        self.telName = ""

        # time delays for various operation

        self.connectDelay = 2 # seconds
        self.dispatchDelay = 2 # seconds
        self.timeDelay = 2 # seconds
        self.queryCadence = 0.1 # seconds - fastest we should emit queries to the controller
        
        # timeouts - can be overrided by the telescope config file entries of the same names

        self.parkTimeout = 60.0 # seconds
        self.slewTimeout = 60.0 # seconds
        
        # minimum declination

        self.minDec = (self.siteLat - 90) + self.minAlt 

        # Useful boolean translation dictionaries

        self.OnOff = {True:"On",False:"Off"}
        self.YesNo = {True:"Yes",False:"No"}

        # USNO NOVAS v3.1 calculation tools from ASCOM.Astrometry.Transform

        self.transform = Dispatch("ASCOM.Astrometry.Transform.Transform")

        # messages, etc.

        self.msg = ""


    # Methods

    #--------------------------------
    #
    # app startup and ASCOM methods
    #


    def connect(self):
        """
        Connect to the STI telescope mount controller app

        Raises
        ------
        RuntimeError
            Raised if it cannot connect to the mount controller.

        Returns
        -------
        None.

        Description
        -----------
        Instantiate a Windows Common Object Module (COM) client ASCOM interface
        instance and connect it to a running PlaneWave STI SiTech Interface
        application.
    
        NOTE: The STI app must be running before using connect()!

        See also: disconnect()
        """

        # instantiate a COM client
        
        try:
            self.tel = Dispatch(self.ASCOM)
            time.sleep(self.dispatchDelay)
        except Exception as exp:
            msg = f"Cannot start {self.ASCOM} COM client: {exp}"
            logger.exception(msg)
            self.tel = None
            self.connected = False
            raise RuntimeError(msg)

        # connect

        try:
            self.tel.Connected = True
            self.connected = True
        except Exception as exp:
            msg = f"Cannot connect to {self.ASCOM}: {exp}"
            logger.exception(msg)
            self.tel = None
            self.connected = False
            raise RuntimeError(msg)

        # we're connected, add connection-time info to the logs
        
        self.telName = self.tel.Description
        logger.info(f"Connected to {self.telName}")
        telAlt = self.tel.Altitude
        telAz = self.tel.Azimuth
        track = self.OnOff[self.tel.Tracking]
        if self.tel.AtPark:
            logger.info(f"At connect telescope is parked at Alt={telAlt:.5f}d, Az={telAz:.5f}d")
        else:
            logger.info(f"At connect telescope is at Alt={telAlt:.5f}d, Az={telAz:.5f} deg, tracking {track}")

 
    def disconnect(self):
        """
        Disconnect from the STI telescope mount controller

        Raises
        ------
        RuntimeError
            Raised if it cannot disconnect from the mount controller.

        Returns
        -------
        None.
        
        Description
        -----------
        Disconnect from the telescope controller and remove the ASCOM object 
        instance.

        See also: connect()
        """
        try:
            self.tel.Connected = False
        except Exception as exp:
            msg = f"Cannot disconnect from the telescope: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        self.connected = False
        self.tel = None
                    
    #------------------------------------
    #
    # Telescope position queries and calculations
    #

    def position(self):
        """
        Read the current telescope pointing information

        Raises
        ------
        RuntimeError
            Raised if it cannot read data from the telescope mount.

        Returns
        -------
        info : dict
            Dictionary of with the telescope pointing data.

        Description
        -----------
        Query the telescope mount controller and retrieve the current
        position of the telescope. The STI controller returns the
        azimuth, altitude, RA, Dec, and LST.
    
        We compute the hour angle HA from the LST and RA and secZ from the 
        telescope altitude and computed HA.
    
        Returns a dictionary with the data (Az, Alt, SecZ, LST, RA, Dec,
        HA) or raises a RuntimeError that usually means the telescope
        isn't connected.

        See also telInfo(), ha(), and secz()
        """
        
        info = {}
        try:
            info['Az'] = self.tel.Azimuth
            telAlt = self.tel.Altitude
            info['Alt'] = telAlt
            
            if telAlt < 1.0:
                info['SecZ'] = 99.99
            else:
                info['SecZ'] = 1.0/math.cos(math.radians(90.0 - telAlt))

            telLST = self.tel.SiderealTime
            info["LST"] = telLST
            telRA = self.tel.RightAscension
            info["RA"] = telRA
            info["Dec"] = self.tel.Declination
            ha = telLST - telRA
            if ha < -12.:  # wrap range -12 to +12h
                ha += 24.
            elif ha > 12.:
                ha -= 24.
            info["HA"] = ha
            return info
        
        except Exception as exp:
            msg = f"Cannot query telescope info - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)


    def telInfo(self):
        """
        Read telescope pointing information for FITS headers

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        fitsInfo : dict
            Dictionary with supplemental FITS header info about the telescope.

        Description
        -----------
        MaxIm DL FITS headers do not include alt, az, HA, or secZ
        in headers, so we query this info and return a FITS-style
        dictionary with the information.  Would be called by
        Camera class object to supplement the default MaxIM FITS header.

        Uses the position() method which also computes HA and secZ

        Returns a dictionary with the missing FITS header data we
        need (Az, Alt, secZ, HA), or it raises a RuntimeError exception
        that usually means the telescopes is not connected.

        The fitsInfo dictionary is formatted FITS-ready for use by
        the demonext Camera object instance.

        See also position(), ha(), and secz()
        """

        fitsInfo = {}
        try:
            fitsInfo['AZ'] = self.tel.Azimuth
            telAlt = self.tel.Altitude
            ha = self.tel.SiderealTime - self.tel.RightAscension
        except Exception as exp:
            msg = f"Cannot query telescope info - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # process data from telescope
        
        fitsInfo['ALT'] = telAlt
        if telAlt < 1.0:
            fitsInfo['SECZ'] = 99.99
        else:
            fitsInfo['SECZ'] = 1.0/math.cos(math.radians(90.0 - telAlt))

        if ha < -12.:  # wrap range -12 to +12h
            ha += 24.
        elif ha > 12.:
            ha -= 24.
        fitsInfo["HA"] = ha
        
        return fitsInfo


    def telFITS(self):
        """
        Return telescope position info as FITS keyword pairs

        Returns
        -------
        info : dict
            Telescope pointing info dictionary with FITS format keywords
        
        Description
        -----------
        Query and return telescope pointing information as FITS format
        strings suitable for FITS headers.
        
        Uses the astropy.coordinates Angle().to_string() method to convert
        decimal angles/hours to sexigesimal strings.
        """
        
        info = {}
        try:
            info["TELAZ"] = Angle(self.tel.Azimuth*u.deg).to_string(sep=":",precision=3,pad=True)
            telAlt = self.tel.Altitude
            info["TELALT"] = Angle(telAlt*u.deg).to_string(sep=":",precision=3,pad=True,alwayssign=True)
            
            # compute Secant(ZD)
            
            if telAlt < 1.0:
                info["SECZ"] = 99.99
            else:
                info["SECZ"] = 1.0/math.cos(math.radians(90.0 - telAlt))

            # local sidereal time
            
            telLST = self.tel.SiderealTime
            info["LST"] = Angle(telLST*u.hour).to_string(sep=":",precision=3,pad=True)
            
            # RA and Dec in sexigesimal 
            
            telRA = self.tel.RightAscension
            telDec = self.tel.Declination
            
            info["TELRA"] = Angle(telRA*u.hour).to_string(sep=":",precision=3,pad=True)
            info["TELDEC"] = Angle(telDec*u.deg).to_string(sep=":",precision=3,pad=True,alwayssign=True)
            
            # compute HA
            
            ha = telLST - telRA
            if ha < -12.:  # wrap range -12 to +12h
                ha += 24.
            elif ha > 12.:
                ha -= 24.
            info["TELHA"] = Angle(ha*u.hour).to_string(sep=":",precision=3,pad=True,alwayssign=True)
            return info
        
        except Exception as exp:
            msg = f"Cannot query telescope pointing info: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
    
        
    def ha(self):
        """compute the current telescope hour angle

        STI controller only reports mount RA, Dec, Alt, Az, and LST,
        so we must compute HA ourselves.

        Returns HA between -12 and 12h, or raise a RuntimeError exception
        that usually means the telescope is not connected.
    
        See also: position(), telInfo()

        """

        try:
            ha = self.tel.SiderealTime - self.tel.RightAscension
            if ha < -12.:  # wrap range -12 to +12h
                ha += 24.
            elif ha > 12.:
                ha -= 24.
            return ha

        except Exception as exp:
            msg = f"Cannot get telescope HA - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
            

    def secz(self):
        """
        compute the secant of the zenight distance of the telescope

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        float
            Secant of Zenith Distance) dimensionless, value of 99.99 if ZD<1 degrees
    
        Description
        -----------
        Compute and return the secant of zenith distance.  Returns
        sec(ZD) if the telescope altitude is above 1-degree, 99.99 if below 1 degree.

        Returns None if no telescope is connected

        Note
        ----
        The secant of the zenith distance angle is sometimes called the
        **Airmass**, but strictly speaking airmass is only approximately 
        sec(ZD) for small zenith distance angles. At larger ZD closer to 
        the horizon this simple geometric approximation breaks down and we
        must resort to atmosphere models that take account of the departure
        of the light path from the simple straight line due to atmospheric
        refraction, different atmosphere layers, etc. needed for elevations 
        less than 10 degrees.

        See also position() and telInfo()
        """

        try:
            telAlt = self.tel.Altitude
            if telAlt < 1.0:
                return 99.99
            else:
                return 1.0/math.cos(math.radians(90.0 - telAlt))

        except Exception as exp:
            msg = f"Cannot get telescope SecZ - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)


    #--------------------------------
    #
    # Query telescope mount state:
    #
    # at home?, at park?, tracking?, slewing?
    #    

    def isHome(self):
        """
        Is the telescope at the home position?

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        boolean
            True if at home, False if away from the home position.

        Description
        -----------
        Is the telescope is at the home position found by seeking the
        edge sensors on the telescope drives?  Returns a True/False
        boolean.

        See also: home(), park(), isParked()
        """
        try:
            return self.tel.AtHome

        except Exception as exp:
            msg = f"Could query telescope position - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        
    def isParked(self):
        """
        Is the telescope parked?

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        boolean
            True if the telescope is parked, False if the telescope is
            out of the parked state.

        See also: park()
        """
        
        try:
            return self.tel.AtPark

        except Exception as exp:
            msg = f"Could query telescope position - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        

    def isTracking(self):
        """
        Is the telescope tracking?

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        boolean
            True if sidereal tracking is ON, False if sidereal tracking is OFF.

    
        See Also: isSlewing()
        """
        
        try:
            return self.tel.Tracking

        except Exception as exp:
            msg = f"Could query telescope tracking - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

    

    def isSlewing(self):
        """
        Is the telescope slewing?

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        boolean
            True if the telescope is slewing between position, False if not 
            slewing (note: sidereal tracking is not considers "slewing")

        See also: isTracking()
        """
        
        try:
            return self.tel.Slewing

        except Exception as exp:
            msg = f"Could query telescope slewing - is telescope connected? - {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

    #--------------------------------
    #
    # Telescope motion commands
    #


    def tracking(self,onoff):
        """
        Turn sidereal tracking on or off

        Parameters
        ----------
        onoff : string
            "on" to start sidereal tracking, "off" to stop sidereal tracking

        Raises
        ------
        ValueError
            Raised if an invalid on/off directive is given.
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        None.

        See also: isTracking()
        """

        if onoff.lower() not in ['on','off']:
            msg = f"Tracking() onoff={onoff} invalid: must be on or off"
            logger.Error(msg)
            raise ValueError(msg)
            return

        try:       
            if onoff.lower() == 'on':
                self.tel.Tracking = True
            else:
                self.tel.Tracking = False
        except Exception as exp:
            msg = f"Cannot turn {onoff.upper()} sidereal tracking: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        logger.info(f"Sidereal tracking is {onoff.upper()}")


    
    def home(self):
        """
        Home the telescope

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        None.

        Description
        -----------
        Homing the telescope instructs the mount to drive the telescope
        to seek the reference "home" sensors on the telescope drive axes.
        These are edge sensors mounted on each of the RA and Dec drive
        gears.
        
        Unlike most STI telescope motion methods, FindHome() is
        synchronous (aka "blocking"): it does not return from the
        ASCOM command until homing has completed.
        
        From the parked position at roughly Az=180, Alt=5 (telescope just
        barely above the fork horizon-pointing), it takes about 30-40
        seconds to home the telescope.
        
        Homing is done at least once per night to reset the telescope's
        position encoders to a known mechanical state.

        See Also: park()
        """
        
        try:
            if self.tel.AtPark:
                self.tel.UnPark
                logger.info("Unparked the telescope")

            time.sleep(self.timeDelay)
        except Exception as exp:
            msg = f"Cannot check telescope park status: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        logger.info("Homing the telescope")

        try:
            self.tel.FindHome
        except Exception as exp:
            msg = f"Cannot start FindHome: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
            
        if self.tel.AtHome:
            logger.info(f"Telescope Homed: Alt={self.tel.Altitude:.5f} Az={self.tel.Azimuth:.5f}")
        else:
            msg = "Cannot home the telescope"
            logger.exception(msg)
            raise RuntimeError(msg)



    def park(self):
        """
        Park the telescope

        Raises
        ------
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        None.

        Description
        -----------
        Park the telescope. This should also turn off the drives, but
        we do it anyway to be certain.

        Parking is non-blocking, so we monitor in a loop that watches the
        self.tel.Slewing boolean and the time of execution relative to
        self.parkTimeout (the maximum time to wait until completion).
        
        After slewing is done, we wait for self.tel.SlewSettleTime before
        completing the operation to give the controller time to settle
        telescope wobble and read the position.  
        
        Note
        ----
        Parking is a coarse pointing operation, and a few percent of the time
        the controller does not set the tel.AtPark property True after parking
        is complete. This condition is benign si we treat it as a warning 
        instead of an exception, and we make sure sidereal tracking is off 
        regardless.

        See also: home(), isParked(), atHome(), unpark()

        """

        try:
            if self.tel.AtPark:
                logger.info(f"Telescope is parked: Alt={self.tel.Altitude:.2f} Az={self.tel.Azimuth:.2f}")
                return
            else:
                logger.info(f"Parking the telescope at Alt={self.parkAlt:.2f} Az={self.parkAz:.2f}...")
        except Exception as exp:
            msg = f"Cannot park the telescope: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        # Start the timer and execute Park

        parkTime = 0.0
        
        try:
            self.tel.Park
        except Exception as exp:
            msg = f"Cannot initiate telescope park: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
            
        t0 = time.time()
        while (self.tel.Slewing and parkTime < self.parkTimeout):
            parkTime = time.time() - t0
            time.sleep(self.queryCadence)

        parkTime = time.time() - t0

        if parkTime >= self.parkTimeout:
            logger.warning(f"Telescope park timed out after {self.parkTimeout} seconds")

        # sleep for slew settle time...

        time.sleep(self.tel.SlewSettleTime)

        # then test for the AtPark=True condition
        
        try:
            isParked = self.tel.AtPark
        except:
            logger.warining("Telescope parking completed, but STI does not verify telescope is parked")
            
        if isParked:
            logger.info(f"Telescope is parked at Alt={self.parkAlt:.2f} Az={self.parkAz:.2f}")
        else:
            logger.warning(f"Park ended at Alt={self.parkAlt:.2f} Az={self.parkAz:.2f} but AtPark=False")

        # last step, turn off tracking

        try:
            self.tel.Tracking = False
            logger.info("Telescope tracking is OFF")
        except Exception as exp:
            msg = f"Cannot verify telescope tracking is OFF: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
            

    def slewToAltAz(self,Alt,Az):
        """
        Slew the tleescope to the requested Alt/Az position

        Parameters
        ----------
        Alt : float
            requested telescope altitude angle in decimal degrees
            range: self.minAlt to 90 degrees (minAlt is typically 5 degrees).
            Alitude 0 degrees is horizon-pointing, 90 degrees is Zenith-pointing
        Az : float
            requested telescope azimuth angle in decimal degrees
            range: 0 to 360 degrees.  Note 180-degrees is pointing due South
            in the northern hemisphere.

        Raises
        ------
        ValueError
            Raised if invalid Alt or Az requested.
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        None.

        Description
        -----------
        Commands the telescope to move to a given  altitude and azimuth.

        This operation is non-blocking, so we monitor progress by watching
        the self.tel.Slewing boolean until False (slewing done) or
        timeout.

        Wait the slew setting time before declaring completion after the
        slew watch loop is complete.

        IMPORTANT NOTE 
        --------------    
        The SiTech.Telescope.SlewToAltAz() method has
        the order of arguments reversed (Az,Alt).  The reason is that
        all ASCOM mount commands have arguments ordered by primary and
        secondary drives, where the secondary drive is carried by the
        primary drive.  This can be confusing, beware!
    
        See also: slewToRADec(), home(), park()
        """

        # validate inputs

        if Alt < self.minAlt or Alt > 90.0:
            msg = f"slewToAltAz(): Alt {Alt:.3f} invalid, must be {self.minAlt:.1f} to 90.0 degrees"
            logger.error(msg)
            raise ValueError(msg)

        if Az < 0 or Az > 360.0:
            msg = f"slewToAltAz(): Az {Az:.3f} invalid, must be 0..360 degrees"
            logger.error(msg)
            raise ValueError(msg)

        # start the timer and execute the move
     
        logger.info(f"Telescope slewing to Alt={Alt} Az={Az}...")

        slewTime = 0.0

        try:
            self.tel.SlewToAltAz(Az,Alt) # note order is Az then Alt, see notes above
        except Exception as exp:
            msg = f"Cannot initiate telescope slew to Alt/Az: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        t0 = time.time()

        while (self.tel.Slewing and slewTime < self.slewTimeout):
            slewTime = time.time() - t0
            time.sleep(self.queryCadence)

        slewTime = time.time() - t0

        if slewTime >= self.slewTimeout:
            logger.warning(f"Telescope slew to Alt/Az timed out after {self.slewTimeout} seconds")

         # sleep for slew settle time...

        time.sleep(self.tel.SlewSettleTime)

        # get Alt/Az at end of motion

        try:
            telAlt = self.tel.Altitude
            telAz = self.tel.Azimuth
            tracking = self.OnOff[self.tel.Tracking]

        except Exception as exp:
            msg = f"Cannot verify telescope position after slew to Alt/Az: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
        logger.info(f"Telescope Alt/Az slew done: Alt={telAlt:.2f} Az={telAz:.2f} Tracking={tracking}")

        
    def slewToRADec(self,appRA,appDec):
        """
        Slew the telescope to the requested RA/Dec coordinates

        Parameters
        ----------
        appRA : float
            Apparent right ascension in decimal hours
            range: 0..24 hours
        appDec : float
            Apparent declination in decimal degrees
            range: minDec to 90 degrees, minDec is at least latitude-90 degrees

        Raises
        ------
        ValueError
            Raised if invalid RA and Dec are given, or the requested
            RA and Dec would drive the telescope out of the operating range.
        RuntimeError
            Raised if it cannot communicate with the mount controller.

        Returns
        -------
        None.

        Description
        -----------
        Commands the telescope to move to the given apparent RA,Dec coordinates.
        Apparent coordinates are those that have been precessed to the
        current observing epoch/equinox from catalog coordinates at a given
        reference equinox like J2000.

        Uses the self.validRADec() method in this class to validate coordinates
        against the mount limits for the time that this command is executed.

        This operation is non-blocking, so we monitor progress by watching
        the self.tel.Slewing boolean until False (slewing done) or
        timeout.

        Waits for the slew setting time before declaring completion after the
        slew watch loop is complete.

        IMPORTANT
        ---------
        The calling program is responsible for predessing catalog coordinates,
        like Equinox J2000, to the current equinox including any
        desired corrections for atmospheric refraction. See the
        precess() method provided in this class for a way to do this that
        is agnostic of the format of the RA/Dec coordinates (decimal or
        sexigesimal).
        
        See also: slewToAltAz(), apparentRADec()
        """
        # validate the requested coordinates

        if not self.validRADec(appRA,appDec):
            msg = f"slewToRADec(): {self.msg}"
            logger.error(msg)
            raise ValueError(msg)

        # start the timer and execute the move
     
        logger.info(f"Telescope slewing to apparent RA={appRA} Dec={appDec}...")

        slewTime = 0.0

        try:
            self.tel.SlewToCoordinates(appRA,appDec)
        except Exception as exp:
            msg = f"Cannot initiate telescope slew to RA/Dec: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)

        t0 = time.time()

        while (self.tel.Slewing and slewTime < self.slewTimeout):
            slewTime = time.time() - t0
            time.sleep(self.queryCadence)

        slewTime = time.time() - t0

        if slewTime >= self.slewTimeout:
            logger.warning(f"Telescope slew to RA/Dec timed out after {self.slewTimeout} seconds")

         # sleep for slew settle time...

        time.sleep(self.tel.SlewSettleTime)

        # get RA/Dec at end of motion

        try:
            telRA = self.tel.RightAscension
            telDec = self.tel.Declination
            tracking = self.OnOff[self.tel.Tracking]

        except Exception as exp:
            msg = f"Cannot verify telescope position after slew to RA/Dec: {exp}"
            logger.exception(msg)
            raise RuntimeError(msg)
        
        logger.info(f"Telescope RA/Dec slew done: RA={telRA:.3f} Dec={telDec:.3f} Tracking={tracking}")

    #--------------------------------
    #
    # Coordinate handling, precession, validation, conversion
    #

    
    def validRADec(self,RA,Dec):
        """
        Validate RA/Dec coordinates against mount limits

        Parameters
        ----------
        RA : float
            Right Ascension in decimal hours.
        Dec : float
            Declination in decimal degrees.

        Returns
        -------
        bool
            True if the RA/Dec are valid to point the telescope within the
            mount limits now, False if the RA/Dec would drive the telescope
            beyond the mount safe limits.

        Description
        -----------
        Tests the validity of RA and Dec against the following criteria:
          * 0 <= RA <= 24 h
          * minDec <= Dec <= 90 d; minDec = siteLat - 90 + minAlt
          * calculated altitude now is < minAlt
          * calculated HA now is minHA <= HAnow <= maxHA

        Returns True if valid, False if not, self.msg contains the
        first test it failed.

        Note that the RA/Dec coordinate equinox is irrelevant for this
        test as the difference between J2000 catalog and current
        equinox is smaller than the limit assertion tolerance.
    
        Calculation is for the current instant in local sidereal time (LST).

        See also: validAltAz()
        """
   
        if RA < 0.0 or RA > 24.0:
            self.msg = f"RA {RA:.3f}h invalid, must be 0..24h"
            return False

        if Dec < self.minDec or Dec > 90.0:
            self.msg = f"Dec {Dec:.3f}d invalid, must be {self.minDec:.1f} to 90 d"
            return False

        # validate requested RA against the HA limits
        
        reqHA = RA - self.tel.SiderealTime
        if reqHA < self.minHA or reqHA > self.maxHA:
            self.msg = f"RA {RA:.3f}h has HA={reqHA:.1f}h outside the {self.minHA:.1f}h to {self.maxHA:.1f}h limits"
            return False

        # validate requested coordinates against the elevation limit

        sinAlt = math.sin(math.radians(Dec))*math.sin(math.radians(self.siteLat)) + math.cos(math.radians(Dec))*math.cos(math.radians(self.siteLat))*math.cos(math.radians(15.0*reqHA))
        if sinAlt < math.sin(math.radians(self.minAlt)):
            alt = math.degrees(math.asin(sinAlt))
            self.msg = f"RA/Dec coordinates have altitude {alt:.2f}d below the minimium altitude of {self.minAlt:.1f} d"
            return False

        self.msg = ""
        return True     


    def validAltAz(self,Alt,Az):
        """
        Validate requested Alt/Az coordinates against the mount limits

        Parameters
        ----------
        Alt : float
            Altitude angle in decimal degrees.
        Az : float
            Azimuth angle in decimal degrees.

        Returns
        -------
        bool
            True if Alt/Az coordinates are within mount limits, False if they
            are outside the mount limits.

        Description
        -----------
        Tests the validity of Alt and Az by the following criteria:
         * minAlt <= Alt <= 90 d; 0 <= RA <= 24 h
         * 0 <= Az <= 360.

        Returns True if valid, False if not, self.msg contains the first test it failed.

        See also: validRADec()
        """
     
        if Alt < self.minAlt or Alt > 90.0:
            self.msg = f"Altitude {Alt:.3f}d is invalid, must be {self.minAlt:.1f} to 90d"
            return False

        if Az < 0.0 or Az > 360.0:
            self.msg = f"Azimuth {Az:.3f}d is invalid, must be 0..360d"
            return False

        self.msg = ""
        return True     


    def precess(self,*args,**kwargs):
        """
        Precess J2000 RA/Dec coordinates to now

        Parameters
        ----------
        *args :
            RA : float/string
                right ascension in hours, may be decimal or sexigesimal
            Dec: float/string
                declination in degrees, may be decimal or sexigesimal

        **kwargs :
            ra : float/string
                right ascension in hours, may be decimal or sexigesimal
            dec : float/string
                declination in degrees, may be decimal or sexigesimal
            frame : string
                coordinate frame, default is 'icrs', may be other valid astropy frame like 'fk5'
            equinox : string
                coordinate equinox, default is "J2000", may be other valid astropy equinox like "B1950"
            unit : duple
                units for ra and dec, default is (u.hour,u.deg), could be (u.deg,u.deg) for RA in degrees
            prec : boolean
                precess coordinates to the current epoch.  Default is True, may be False if you really want...
                
        Raises
        ------
        ValueError
            Raised if invalid input sare provided.
        RuntimeError
            Raised if exception raised by astropy.coordinates.SkyCoord() are raised

        Returns
        -------
        float
            apparent right ascension in decimal hours.
        float
            apparent declination in decimal hours.

        Description
        -----------
              
        Uses astropy.coordinates.SkyCoord() and astropy.units to agnostically
        read any sensible format for RA and Dec in J2000 equinox and precess
        these catalog coordinates to the current time.  Also uses the 
        astropy.time Time method and astropy.coordinates TETE system.

        Returns RA in decimal hours and Dec in decimal degrees precessed to the
        current epoch/equinox (aka "apparent RA and Dec" as used by the SiTech
        telescope controller).
                
        We use the True Equator and True Equinox (TETE) system for precession, 
        computing "apparent coordinates" for the pointing the telescope using
        catalog ICRS or FK5 coordinates in J2000 equinox.
    
        Example
        -------  
        Acceptable usage:
            
        >>> appRA, appDec = tel.precess(18.25,24.50)
        >>> appRA, appDec = tel.precess("18:15:00.0","+24:30:00")
        >>> appRA, appDec = tel.precess("18:15:00 +24:30:00.00")
        >>> appRA, appDec = tel.precess(ra=18.25,dec=24.50)
        >>> appRA, appDec = tel.precess(ra="18:15:00",dec=24.50)
        >>> appRA, appDec = tel.precess(ra="18:15:00",dec="+24:30:00")
        
        We benefit from how flexibly the SkyCoord() method was designed.
  
        """
    
        # defaults: ICRS frame, J2000 equinox, RA in hours, Dec in degrees
    
        frame="icrs"
        equinox="J2000"
        unit = (u.hour,u.deg)
        prec = True
    
        # different ways to pass coordinates
    
        if len(args)==2:
            ra2000 = args[0]   # traditional no keywords: myCoords(ra,dec)
            dec2000 = args[1]
        elif len(args)==1:
            try:
                ra2000, dec2000 = args[0].split(" ") # one string: myCoords("rastr decstr")
            except Exception as exp:
                raise ValueError(f"badly-formatted coordinates '{args[0]}': {exp}")
    
        if len(kwargs)>0:
            for key, val in kwargs.items(): # by keywords: myCoords(ra=.., dec=.., equinox="B1950", ...)
                if key == "ra":
                    ra2000 = val
                elif key == "dec":
                    dec2000 = val
                elif key == "frame":
                    frame = val
                elif key == "equinox":
                    equinox = val
                elif key == "unit":
                    unit = val
                elif key == "prec":
                    prec = val
                else:
                    raise ValueError(f"Invalid argument {key}={val}")

        # SkyCoord object for input coordinates, catch possible exception here
    
        try:
            targ2000 = SkyCoord(ra=ra2000,dec=dec2000,unit=unit,frame=frame,equinox=equinox)
        except Exception as exp:
            raise RuntimeError(f"Bad inputs: {exp}")
    
        # precess input coordinates to now or if prec=False, return decimal version of input coords
    
        if prec:
            appTarg = targ2000.transform_to(TETE(obstime=Time.now()))
            return appTarg.ra.hour, appTarg.dec.deg
        else:
            return targ2000.ra.hour, targ2000.dec.deg


    def apparentRADec(self,RAJ2000,DecJ2000):
        """
        Precess J2000 RA/Dec to apparetn RA/Dec now

        Parameters
        ----------
        RAJ2000 : float
            Right Ascension in J2000 equinox in decimal hours.
        DecJ2000 : float
            Declination in J2000 equinox in decimal degrees.

        Returns
        -------
        float
            Appparent RA in decimal hours.
        float
            Apparent Dec in decimal hours.

        Description
        -----------
        Computes apparent RA, Dec at the current epoch/equinox given
        catalog coordinates in J2000 equinox.

        This version the ASCOM Astrometry.Transform object which implements
        the US Naval Observatory NOVAS3.1 library calculator to convert J2000
        equinox coordinates to apparent RA/Dec in the equinox/epoch now.
        
        This is an alternative to using astropy. It gives the same number
        within a few milliarcsec.  We ported this here from the original
        2016 DEMONEXT python 2 code for reference and testing, but
        deprecate its use.
        
        """
        
        self.transform.SetJ2000(RAJ2000,DecJ2000)
        return self.transform.RAApparent, self.transform.DECApparent

    #------------------------------------
    #
    # decimal <-> sexigesimal conversion
    #
    
    def dec2sex(self,decAng,precision=2,sign=False):
        """
        Convert decimal angle into a sexigesmial string

        Parameters
        ----------
        decAng : float
            angle, either degrees or hours.
        precision : int, optional
            precision of the seconds part. The default is 2.
        sign : boolea, optional
            include + sign if decAng>0. The default is False (no + sign).

        Returns
        -------
        string
            Sexigesimal string representation of decAng with a colon (:)
            separator.
            
        See Also
        --------
        sex2dec

        """    

        return Angle(decAng,unit=u.deg).to_string(sep=":",precision=precision,pad=True,alwayssign=sign)


    def sex2dec(self,sexStr,precision=8):
        """
        Convert a sexigesimal string to decimal

        Parameters
        ----------
        sexStr : string
            sexigesimal representation of an angle (see Notes)
        precision : integer, optional
            precision of the conversion. The default is 8 figures beyond the decimal point.

        Returns
        -------
        float
            decimal representation of the sexigesimal string
            
        Notes
        -----
        If the string is in 12h13m18.23s format, the "h" will make sure the
        conversion preserves units of hours.  Correctly recognizes strings
        that don't use the colon (:) separator, so 12:13:14.15 = 12d13m14.15s and 12:13:14.15 = 12h13m14.5s preserve
        correct hours or degrees units on the conversion to decimal
                
        See Also
        --------
        dec2sex

        """
        if "h" in sexStr:
            units = u.hour
        else:
            units = u.deg
        return float(Angle(sexStr,unit=units).to_string(decimal=True,precision=precision))
    
    
    
    
    
    
    
