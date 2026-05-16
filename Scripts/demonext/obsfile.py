"""DEMONEXT ObsFile observation file class

DEMONEXT uses YAML to format observation files that are used to make
a "unit" observation.  This class provides tools to read and condition
the contents of an observation file, creating the parameters used to
execute an observation with the Telescope and Camera classes.

Author:
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2025 Jan 29

Modification History:
   2025 Jan 29 - first version, based on the Config class [rwp/osu]
   2025 Jan 30 - added precess(), changes from live test [rwp/osu]
   2025 Apr 28 - edits as we develop the obs file syntax [rwp/osu]
   2025 Apr 30 - live test updates, augment projInfo dict [rwp/osu]
   
"""

import os

# we use yaml for observation file parsing

import yaml

# logging

import logging
logger = logging.getLogger("ObsFile")

# astropy units, coordinates, and times

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.coordinates import TETE
from astropy.time import Time

# ObsFile Class

class ObsFile:
    """YAML observation file handling class
    
    Methods
    -------
    __init__(obsFile)
        initialize the ObsFile class instance
       
        obsFile : string
            full name of the YAML observation file to load.
    precess()
        precess J2000 RA/Dec coordinates to apparent RA/Dec coordinates now
    execTime()
        estimate the total execution time including overheads [future]
    
    Properties
    ----------
    obsFile : string
        name of the observation file
    obs : dict of dicts
        observation parameter dictionary (whole YAML dump)
    dicts : string list
        list of observation dictionary primary keywords
    projInfo : dictionary
        project information dictionary in FITS-like format
    targInfo : dictionary
        target info (name, RA, Dec, Priority, GuideMode)
    obsInfo : dictionary
        observing sequence dictionary
    conInfo : dictionary
        observation constraints dictionary
    statusInfo: dictionary
        observing file internal status dictionary
    object : string
        object name
    RA : string
        object J2000 right ascension in sexigesimal hours format
    Dec : string
        object J2000 declination in sexigesimal degrees format
    appRA : float
        object apparent right ascension in decimal hours (output of precess() method)
    appDec : float
        object apparent declination in decimal degrees (output of precess() method)
    guideMode : string
        guiding mode, one of auto, science or none (unguided)
    priority: int
        target priority, 1=highest, 3=lowest, default=1
    numObs : int
        number of time to execute the observing sequence (default: 1)
    numItems : int
        number of items in the observing sequence (e.g., 3 filters)
    obsPars : list of lists
        observation parameters, one for each observation in the sequence.  Format
        is [filterID,expTime,numImages]
    airmass : float
        maximum airmass or None if no airmass constraint
    moonAngle : float
        minimum moon angle in degrees or None if no moon angle constraint
    moonPhase : float
        maximum Moon phase (0=dark, 1=full) or None if no moon phase constraint
    maxSky : float
        maximum sky level per pixel in adu or None if no sky brightness constraint
    startTime : string
        UTC starting time/date constraint in ISO8601-compliant CCYY-MM-DDThh:mm:ss.sZ or None if no start time contraint
    endTime : string
        UTC ending time/date constraint in ISO8601-compliant CCYY-MM-DDThh:mm:ss.sZ or None if no end time contraint
        
    """
    
   
    def __init__(self,obsFile):
        """
        Initialize a ObsFile class instance.

        Parameters
        ----------
        obsFile : string, optional
            name (including path) of a YAML observation file

        Raises
        ------
        RuntimeError
            Raised if the observation file is not found or cannot be opened.

        Returns
        -------
        None.
       
        Description
        -----------
        Initialize an `ObsFile` class instance and open and load the named
        observation file, populating the class properties.
    
        """

        # we require an observation file and it must exist
        
        if len(obsFile) > 0:
            if os.path.exists(obsFile):
                self.obsFile = obsFile
            else:
                msg = f"Observation file {obsFile} not found"
                logger.error(msg)
                raise ValueError(msg)
        else:
            msg = "No observation file given"
            logger.error(msg)
            raise ValueError(msg)
    
        # initializations of dictionary properties

        self.obs = {} # empty dictionary to contain the contents of the observation file
        self.dicts = [] # empty list of observation file dictionaries

        # observation file component dictionaries
        
        self.projInfo = {}   # project information dictionary
        self.targInfo = {}   # target information dictionary
        self.obsInfo = {}    # observation sequence dictionary
        self.conInfo = {}    # observation constraint dictionary
        self.statusInfo = {} # observing file internal status dictionary
        
        # we have a observation file, open readonly and load using yaml.safe_load()

        with open(self.obsFile,"r") as stream:
            try:
                self.obs = yaml.safe_load(stream)
            except yaml.YAMLError as exp:
                msg = f"Cannot open observation file {self.obsFile}: {exp}"
                logger.exception(msg)
                raise RuntimeError(msg)
        
        # build the list of dictionaries in the observation file

        self.dicts = list(self.obs.keys())

        # populate the dictionaries from an observation file
            
        if "project" in self.dicts:
            self.projInfo = self.obs["project"]
        if "target" in self.dicts:
            self.targInfo = self.obs["target"]
        if "sequence" in self.dicts:
            self.obsInfo = self.obs["sequence"]
        if "constraints" in self.dicts:
            self.conInfo = self.obs["constraints"]
        if "status" in self.dicts:
            self.statusInfo = self.obs["status"]
            
        # Break out those items in the observation file dictionary we
        # assign to class properties.
            
        # Target info
        
        # Name: target name
        
        try:
            self.name = self.targInfo["Name"]
        except:
            self.name = None

        # RA2000 and Dec2000: target J2000 coordinates
        
        try:
            self.RA = self.targInfo["RA2000"]
        except:
            self.RA = None
            
        try:
            self.Dec = self.targInfo["Dec2000"]
        except:
            self.Dec = None

        # priority: observing queue priority (used by the scheduler)
        #           default: 1, range 1=highest, 3=lowest
        
        try:
            self.priority = self.targInfo["Priority"]
        except:
            self.priority = 1

        # GuideMode: guiding mode to use, must be one of {science,auto,none}
        #            default: guideMode = None if missing   
        
        try:
            self.guideMode = self.targInfo["GuideMode"]
            if self.guideMode not in ["science","auto","none"]:
                msg = f"Invalid GuideMode {self.guideMode}, must be science, auto, or none - setting none"
                logger.warning(msg)
                self.guideMode = None
        except:
            self.guideMode = None
                    
        # precess (RA2000,Dec2000) coordinates to the current epoch
            
        try:
            self.precess()
        except:
            self.appRA = None
            self.appDec = None
            
        # Observation sequence info
        
        # NumObs: how many times to execute the observation sequence
        #         default is once (numObs=1) if omitted
        # NumItems: number of items in the observing sequence
        
        try:
            self.numObs = self.obsInfo["NumObs"]
            self.numItems = len(self.obsInfo.keys()) - 1
        except:
            self.numObs = 1
            self.numItems = len(self.obsInfo.keys())
                   
        # the unit observations that make up a sequence are
        # numbered obs1, obs2, ..., obsN and are lists
        #  ["filterID",expTime,numImgs]
        
        self.obsPars = [] # list of observing parameter lists
        for i in range(self.numItems):
            key = f"obs{i+1}"
            self.obsPars.append(self.obsInfo[key])
       
        # Observing constraints
        
        try:
            self.airmass = self.conInfo["Airmass"]
        except:
            self.airmass = None
        
        try:
            self.moonAngle = self.conInfo["MoonAngle"]
        except:
            self.moonAngle = None
            
        try:
            self.moonPhase = self.conInfo["MoonPhase"]
        except:
            self.moonPhase = None
            
        try:
            self.maxSky = self.conInfo["MaxSky"]
        except:
            self.maxSky = None
            
        try:
            self.startTime = self.conInfo["StartTime"]
        except:
            self.startTime = None
            
        try:
            self.endTime = self.conInfo["EndTime"]
        except:
            self.endTime = None
            
        # Augment the projInfo dictionary with additional information
        # we want in the image FITS headers 
        
        if self.RA:
            self.projInfo['TARG_RA'] = self.RA
        if self.Dec:
            self.projInfo['TARG_DEC'] = self.Dec
        self.projInfo['OBSFILE'] = self.obsFile
        self.projInfo['PRIORITY'] = self.priority
        if self.guideMode:
            self.projInfo['GUIDING'] = self.guideMode
        else:
            self.projInfo['GUIDING'] = 'None'

    #----------------------------------------
    #
    # Methods
    #

    def precess(self):
        """
        Precess observation file J2000 RA/Dec coordinates to now

        Raises
        ------
        ValueError
            Raised if invalid coordinates were provided.
        RuntimeError
            Raised if exception raised by astropy.coordinates.SkyCoord() are raised

        Returns
        -------
        appRA : float
            apparent right ascension in decimal hours.
        appDec : float
            apparent declination in decimal hours.

        Description
        -----------
              
        Uses `astropy.coordinates.SkyCoord()`, `astropy.time.Time`, and 
        `astropy.units` to convert observation file RA and Dec in J2000 
        equinox and precess them to the current epoch ready for telescope pointing.

        Returns RA in decimal hours and Dec in decimal degrees precessed to the
        current epoch/equinox (aka "apparent RA and Dec" as used by the SiTech
        telescope controller).
                
        We use the True Equator and True Equinox (TETE) system for precession, 
        computing "apparent coordinates" for the pointing the telescope using
        catalog ICRS or FK5 coordinates in J2000 equinox.
        
        This is a minimalist version of the Telescope class `precess()`
        method since we know we are getting properly-formatted RA/Dec
        in sexigesimal form.  Or we better...
    
        """
    
        # defaults: ICRS frame, J2000 equinox, RA in hours, Dec in degrees
    
        frame="icrs"
        equinox="J2000"
        unit = (u.hour,u.deg)
    
        if not self.RA or not self.Dec:
            msg = "No RA/Dec coordinates to process"
            raise ValueError(msg)

        # SkyCoord object for input coordinates, catch possible exception here
    
        try:
            targ2000 = SkyCoord(ra=self.RA,dec=self.Dec,unit=unit,frame=frame,equinox=equinox)
        except Exception as exp:
            raise RuntimeError(f"Bad RA/Dec given: {exp}")
    
        # precess input coordinates to now, returning decimal hours and degrees
    
        appTarg = targ2000.transform_to(TETE(obstime=Time.now()))
        self.appRA = appTarg.ra.hour
        self.appDec = appTarg.dec.deg
    
        return self.appRA, self.appDec


    def print(self):
        """
        Print the contents of the observation file.
        
        Returns
        -------
        None.
        
        Description
        -----------
        Formatted print to stdout of the contents of the YAML observation
        file contents in human-readable form.  If no observation file was
        loaded it says that and does not raise a exception.
        """
        
        if self.obsFile is None:
            print("No observation file has been loaded")
        else:
            print(f"\nObservation file {self.obsFile} contents:")
            for key in self.obs:
                if isinstance(self.obs[key],dict):
                    print(f"\n{key}:")
                    yamlItem = self.obs[key]
                    for keyword in yamlItem:
                        print(f"  {keyword}: {yamlItem[keyword]}")
                else:
                    print(f"{key}: {self.obs[key]}")


