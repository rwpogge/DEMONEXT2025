"""DEMONEXT Observatory Site interface class

Class to provice site-specific calculations for the DEMONEXT observatory
system.  Uses astropy and astroplan

Author:
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2025 June 4

Modification History:
   2026 Mar 29 - added SRO roof and weather info after live tests at SRO [rwp/osu]

"""

import os
import time
import math

# pathlib for path handling

from pathlib import Path

# yaml for configuration file parsing

import yaml

# logging

import logging
logger = logging.getLogger("Site") 

# astropy units, coordinates, and times

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.coordinates import Angle
from astropy.coordinates import EarthLocation
from astropy.time import Time

# astroplan for observing circumstances calculations (sunset etc.)

from astroplan import Observer

# timezone info using pytz

from pytz import timezone

# Site Class

class Site:
    """Observatory Site utilities class

    Provides site-specific calculations for the DEMONEXT observatory
    including time, sun position, etc.

    Methods
    -------
    __init__(cfgFile,args)
        initialize the Site class instance
       
        cfgFile: string
            full name of the YAML runtime configuration file to load.
            default: looks in $HOME for `.demonext/config/demonext.txt`
    sunAlt()
        what is the current altitude of the Sun relative to the horizon
    isNight()
        is it night (sun below the horizon)?
    isDark() 
        is it dark (sun more than 18-degrees below the horizon)?
    isTwilight(twAlt=-12)
        is it twilight (sun -12 to -18-degrees below the horizon)?
    getRoof() 
        retrieve info on the building roof status (roof dictionary)
    roofOpen()
        is the building's roof open (True) or closed (False)
    getWeather()
        get site weather station data (weather dictionary)
    siteTelemetry()
        return site weather and roof info as FITS keywords for headers
    f2c()
        convert temperature in Fahrenheit to Celsius
    mph2ms()
        convert speed in miles/hour to meters/second
    knots2ms()
        convert speed in knots to meters/second
            
    Attributes
    ----------
    obs : astroplan Observer object
        astroplan observer object for this observatory site
    msg : string
        internal message string
    siteInfo: dict
        observatory site info as FITS keywords
    roof : dict
        Building roof status dictionary
    weather : dict
        Site weather information dictionary

    """
    
    def __init__(self,*args):
        """
        Initialize the Site class

        Parameters
        ----------
        *args :
            cfgFile : string
                Name and path of a YAML runtime configuration file with the
                site information
                
        Raises
        ------
        RuntimeError
            Raised if errors reading the configuration file

        Returns
        -------
        None.

        Description
        -----------
        The constructor initializes all data structures and properties
        needed to compute site-specific information like sun position
        at the present time.
        
        If no runtime configuration file is given, it defaults to a file 
        named demonext.txt in the user .demonext/config/ directory 
        (default expectation).  We load it directly rather than using
        the Config class.

        """
        # Default observing site
        
        self.siteName = "Sierra Remote Observatories"
        self.siteLon = -119.41293
        self.siteLat = 37.07031
        self.siteElev = 1405.0  
        self.siteTZ = "US/Pacific"

        # Argument options from nothing, a config file, or individual keywords
        
        if len(args) > 0:
            cfgFile = args[0]
        
        else:  # default config file
            cfgFile = str(Path.home() / ".demonext/config/demonext.txt")

        # open the configuration file and get the info we need for the telescope
        
        if cfgFile is not None:
            if os.path.exists(cfgFile):
                with open(cfgFile,"r") as stream:
                    try:
                        config = yaml.safe_load(stream)
                    except yaml.YAMLError as exp:
                        msg = f"Cannot open runtime configuration file {cfgFile}: {exp}"
                        logger.exception(msg)
                        raise RuntimeError(msg)

                # observatory site info
                
                try:
                    self.siteInfo = config["site"]
                except:
                    self.siteInfo = None
                
                # site telemetry (weather, roof, etc.) directories
                
                try:
                    tmpDir = config["directories"]["RoofDir"]
                    if len(Path(tmpDir).root) == 0: # rootless, assume relative to home
                        self.roofDir = str(Path.home() / tmpDir)
                    else:
                        self.roofDir = tmpDir
                except:
                    self.roofDir = None

                try:
                    tmpDir = config["directories"]["WeatherDir"]
                    if len(Path(tmpDir).root) == 0: # rootless, assume relative to home
                        self.weatherDir = str(Path.home() / tmpDir)
                    else:
                        self.weatherDir = tmpDir
                except:
                    self.weatherDir = None

                # site roof and weather files

                try:
                    tmpFile = config["telemetry"]["RoofFile"]
                    self.roofFile = Path(self.roofDir) / tmpFile
                except:
                    self.roofFile = None
                    
                try:
                    tmpFile = config["telemetry"]["WxFile"]
                    self.weatherFile = Path(self.weatherDir) / tmpFile
                except:
                    self.weatherFile = None

            else:
                msg = f"Runtime configuration file {cfgFile} does not exist"
                logger.exception(msg)
                raise RuntimeError(msg)

        # Extract site info from the configuration file 

        if self.siteInfo:
            if "SITENAME" in self.siteInfo:
                self.siteName = self.siteInfo["SITENAME"]
            if "SITE_LON" in self.siteInfo:
                self.siteLon = self.siteInfo["SITE_LON"]
            if "SITE_LAT" in self.siteInfo:
                self.siteLat = self.siteInfo["SITE_LAT"]
            if "SITE_EL" in self.siteInfo:
                self.siteElev = self.siteInfo["SITE_EL"]           
            if "SITE_TZ" in self.siteInfo:
                self.siteTZ = self.siteInfo["SITE_TZ"]
        
        # Instantiate an astroplan Observer object for the site
        
        try:
            siteLoc = EarthLocation.from_geodetic(self.siteLon,self.siteLat,self.siteElev)
        except Exception as exp:
            self.msg = f"Bad site information passed to EarthLocation(): {exp}"
            raise RuntimeError(self.msg)            

        try:        
            self.obs = Observer(location=siteLoc,name=self.siteName,timezone=timezone(self.siteTZ))
        except Exception as exp:
            self.msg = f"Bad site information passed to Observer(): {exp}"
            raise RuntimeError(self.msg)            
        
        # Useful boolean translation dictionaries

        self.OnOff = {True:"On",False:"Off"}
        self.YesNo = {True:"Yes",False:"No"}

        # empty roof and weather data dictionaries
        
        self.roof = {}
        self.weather = {}
        
        # messages, etc.

        self.msg = ""


    #-----------------------------
    #
    # Sun position methods
    #
    
    def sunAlt(self):
        """
        Compute the altitude of the sun now relative to the horizon

        Returns
        -------
        sunAlt: float
            sun altitude in decimal degrees
            
        Description
        -----------
        Computes the instantaneous (now) altitude of the Sun relative to the
        local horizon using astroplan.  Returns the altitude in decimal degrees.
        
        See also isNight, isDark, isTwilight
        """

        sunPos = self.obs.sun_altaz(Time.now())
        return sunPos.alt.value
    

    def isNight(self):
        """
        Is it night?

        Returns
        -------
        bool
            True if the sun is below the local horizon
        
        Description
        -----------
        Night is defined as when the Sun is below the local horizon (alt=0 deg)
        as computed at the current time.
        
        See also isDark, isTwilight, sunAlt        
        """
        
        return self.obs.is_night(Time.now())


    def isDark(self):
        """
        Is it dark?

        Returns
        -------
        bool
            True if the sun is more than 18-degrees below the local horizon
        
        Description
        -----------
        Darkness is defined as when the sun is more than 18-degrees below
        the local horizon.  This is the definition of "astronomical twilight"
        in standard astronomical usage.
        
        This is a convenicence function using sunAlt()
        
        See also isNight, sunAlt        
        """
        
        return (self.sunAlt() <= -18.0) 
    
    
    def isTwilight(self,twAlt=-12.0):
        """
        Is it twilight?

        Parameters
        ----------
        twAlt : float, optional
            Altitude of the Sun to use. The default is -12.0.

        Returns
        -------
        bool: True if the sun altitude is -18 <= sunAlt <= twAlt
        
        Description
        -----------
        Test to see if the site is in twilight.  We define the
        default onset of twilight to be "nautical twilight", when the
        Sun is between 12 and 18 degress below the local horizon.
        
        Users can test other twilight definitions, for example
        defining onset of twilight as "civil twilight" which is the Sun
        between 6 and 18 degrees below the horizon.
        
        See also isNight, isDark, sunAlt
        """
        
        altNow = self.sunAlt()
        return (altNow >= -18.0 and altNow <= twAlt)
    
    
    #------------------------------------------------
    #
    # Building roof status methods
    #
    
    def getRoof(self):
        """
        Retrieve building roof information

        Returns
        -------
        bool
            True if got roof into, False if errors
        
        Description
        -----------
        Read and parse the roof data file on the SRO site server machine.
        
        On errors it sets roof["error"] True and puts error info in self.msg
        otherwise it sets the roof dictionary entries:
         * date: string, local date roof data was updated
         * time: string, local time roof data was updated
         * iso: string, local date/time in ISO 8601 format
         * position: string, OPEN, CLOSED, or UNKNOWN on errors
         * open: bool, True of roof is open, False if closed or unknown
         * error: bool, True if read OK, False if errors on opening or reading
         * message: string, success or error message
         
        The log is updated every time this method is called.
        
        See Also
        --------
        roofOpen() method

        """
        self.roof = {}
        try:
            with open(self.roofFile,"r",encoding="utf-8") as file:
                data = file.read()
                roofData = data.strip().split()
                self.roof["date"] = roofData[0][3:] # first 3 bytes are ???, skip
                self.roof["time"] = roofData[1][:8]
                self.roof["iso"] = f"{roofData[0][3:]}T{roofData[1][:8]}" # ISO 8601 date/time format
                self.roof["position"] = roofData[4]
                if roofData[4] == "OPEN":
                    self.roof["open"] = True
                else:
                    self.roof["open"] = False
                self.roof["error"] = False
                self.msg = "Read roof data"
                logger.info(f'Roof is {self.roof["position"]}')

                
        except FileNotFoundError:
            self.roof["error"] = True
            self.msg = f"Roof status file {self.roofFile} not found"
            self.roof["open"] = False
            self.roof["position"] = "UNKNOWN"
            logger.error(self.msg)
            return False
        
        except IOError as err:
            self.roof["error"] = True
            self.msg = f"Cannot read roof file {self.roofFile} - {err}"
            self.roof["open"] = False
            self.roof["position"] = "UNKNOWN"
            logger.error(self.msg)
            return False
        
        return True        
        
    
    def roofOpen(self):
        """
        Read the Roof file and return the roof state

        Returns
        -------
        bool
            True if the roof is open, False if closed or state unknown

        Description
        -----------
        Reads the SRO building roof data with getRoof() and
        returns True if the roof is open, False if closed or 
        state unknown.  State can be retrieved from the roof['position']
        string.
        
        Roof status is updated every 10 seconds.
        
        See Also
        --------
        getRoof()
        
        """
        if self.getRoof():
            return self.roof["open"]
        else:
            return False
        
    
    #------------------------------------------------
    #
    # Observatory site weather information methods
    #

    def f2c(self,tempF):
        """
        Convert Fahrenheit to Celsius

        Parameters
        ----------
        tempF : float
            Temperature in degrees Fahrenheit.

        Returns
        -------
        float
            Temperature in degrees Celsius.

        """
        return (tempF - 32.0)/1.8


    def mph2ms(self,mph):
        """
        Convert speed in miles/hour to meters/second

        Parameters
        ----------
        mph : float
            Speed in miles per hour.

        Returns
        -------
        float
            Speed in meters per second.
            
        Description
        -----------
        Units conversion is purposefully explicit instead of using an
        approximation so the provenance is clear:
         * 1 statute mile = 5280 feet
         * 1 foot = 12 inches
         * 1 inch = 0.0254 meters
         * 1 hour = 3600 seconds
         
        """
        return (12*5280*0.0254)*mph/3600.0


    def knots2ms(self,knots):
        """
        Convert speed in knots to meters per second
        
        Parameters
        ----------
        knots : float
            Speed in knots (1 nautical mile per hour)

        Returns
        -------
        float
            Speed in meters per second.

        Description
        -----------
        Units conversion is purposely explicitly instead of using an
        approximations so the provenance is clear:
         * 1 nautical mile = 1852 meters (Gobel et al. 2006, The SI Units, Table 8)
         * 1 hour = 3600 seconds

        """
        return 1852.0*knots/3600.0


    def getWeather(self):
        """
        Retrieve weather data from the SRO weather service

        Returns
        -------
        bool
            True if weather data read, False on errors
            
        Description
        -----------
        Read and parse the site weather data file on the SRO site server machine.
        On errors set self.msg with why and return False

        Weather data at SRO is stored in "Boltwood II" one-line format 
        (https://interactiveastronomy.com/skyroof_help/Weatherdatafile.html)
        on the observatory site server.  
        
        We open and parse the weather file and retrieve the information we
        need. Weather information is updated every 20 seconds when the
        weather station is operating.

        """
        self.weather = {}

        # Translations of different flag codes
 
        cloudFlags = ["Unknown","clear","light clouds","cloudy"]
        windFlags = ["Unknown","calm","windy","very windy"]
        rainFlags = ["Unknown","dry","damp","rain"]
        darkFlags = ["Unknown","dark","dim","daylight"]

        # Read and parse the weather file
 
        try:
            with open(self.weatherFile,"r",encoding="utf-8") as file:
                data = file.read()
                wxData = data.strip().split()
                # print(wxData)
                self.weather["up"] = True
                self.weather["date"] = wxData[0]
                self.weather["time"] = wxData[1]
                self.weather["iso"] = f"{wxData[0]}T{wxData[1][:8]}" # ISO 8601 date/time format
                tempUnits = wxData[2]
                windUnits = wxData[3]

                # convert temperatures from Fahrenheit to Celsius as needed
         
                if tempUnits == "F":
                    self.weather["skyTemp"] = self.f2c(float(wxData[4]))
                    self.weather["airTemp"] =  self.f2c(float(wxData[5]))
                    self.weather["dewpoint"] = self.f2c(float(wxData[9]))
                else:
                    self.weather["skyTemp"] = float(wxData[4])
                    self.weather["airTemp"] = float(wxData[5])
                    self.weather["dewpoint"] = float(wxData[9])

                # convert wind speed from mph or knots to m/s as needed
         
                if windUnits == "M":
                    self.weather["windspeed"] = self.mph2ms(float(wxData[7]))
                else:
                    self.weather["windspeed"] = self.knots2ms(float(wxData[7]))                    
         
                self.weather["humidity"] = float(wxData[8])
                self.weather["rain"] = rainFlags[int(wxData[17])]
                self.weather["damp"] = int(wxData[12])
                self.weather["clouds"] = cloudFlags[int(wxData[15])]
                self.weather["winds"] = windFlags[int(wxData[16])]
                self.weather["sky"] = darkFlags[int(wxData[18])] 
                self.msg = "Read SRO weather station data"
                
        except FileNotFoundError:
            self.weather["up"] = False
            self.msg = f"SRO weather file {self.weatherFile} not found"
            logger.error(self.msg)
        
        except IOError as err:
            self.weather["up"] = False
            self.msg = f"Cannot read SRO weather file {self.weatherFile} - {err}"
            logger.error(self.msg)

        return self.weather["up"]
    
    
    def siteTelemetry(self):
        """
        Returns observing site weather and roof telemetry as FITS keyword pairs

        Returns
        -------
        info : dict
            Site weather info dictionary with FITS format keywords
            
        Description
        -----------
        Query and return SRO site weather and roof status telemetry as FITS format
        keyword/value pairs.
        
        """
        info = {}
        
        # Buiding roof status
        
        self.getRoof()
        info["SRO_ROOF"] = self.roof["position"]

        # Select weather info
        
        if self.getWeather():
            info["SRO_LINK"] = "UP"
            info["SRO_TEMP"] = f'{self.weather["airTemp"]:.1f}'
            info["SRO_HUM"] = f'{self.weather["humidity"]:.1f}'
            info["SRO_DEWP"] = f'{self.weather["dewpoint"]:.1f}'
            info["SRO_WIND"] = f'{self.weather["winds"]}, {self.weather["windspeed"]:.2f} m/s'
            info["SRO_SKY"] = f'{self.weather["clouds"]}, {self.weather["rain"]}, {self.weather["sky"]}, {self.weather["skyTemp"]:.1f} C'
        else:
            info["SRO_LINK"] = "DOWN"
            
        return info
