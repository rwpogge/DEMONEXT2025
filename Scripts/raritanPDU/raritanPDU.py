"""Raritan PDU interface class

Custom class to remotely operate a Raritan power-distribution unit (PDU) using
the Raritan's JSON-RPC API python bindings.  Designed for a Raritan PXO unit
with 4 unmetered outlets and 1 metered inlet, which makes this relatively 
minimalist compared to the range of PDU functions in higher models.

Author:
  R. Pogge, OSU Astronomy Dept.
  pogge.1@osu.edu
  2024 Dec 9

Modification History:
  2024 Dec 09 - first version [rwp/osu]
  2024 Dec 10 - added using yaml for reading config, changed __init__() [rwp]
  2024 Dec 11 - choice of cfgFile or kwargs [rwp/osu]

Deprecation Note:
  Standalone version for test and evaluation, for DEMONEXT use the later version
  of the raritanPDU() class in config.py
  
"""

import os
import time

# Raritan JSON-RPC API python client bindings

from raritan import rpc
from raritan.rpc import pdumodel
from raritan.rpc import peripheral

# pathlib for path handling

from pathlib import Path

# yaml for configuration file parsing

import yaml

# raritanPDU Class

class raritanPDU:

    """Raritan PDU JSON-RPC interface class

    Arguments:
       cfgFile - (string) YAML configuration file (including path) with PDU info

    kwargs arguments:
       ipaddr - (string) IP address of the Raritan PDU
       userid - (string) username on the Raritan
       passwd - (string) password for username
       nocert - (bool) True for no certificate, False for require certificate
       outlets - (string list) names to bind to outlets 1..N
    
    Initialize the Raritan JSON-RPC interface and retrieve info we need to query
    and command the PDU.  The PDU connection info (IP address, user, and password)
    are kept in the YAML runtime configuration file as the "pdu" entry.  We expect
    
    The constructor establishes the RPC agent, model, and peripheral manager
    needed to access PDU functions and data by class member functions and properties.

    If a config file is given as the argument, it expects a YAML formatted file
    with the "pdu" dictionary entry with 5 parameters:
       ipAddr - the IP address
       userID - the username on the Raritan (should be operator instead of admin)
       passwd - the password for userID
       disableCert - disable certification verification.  If missing, default True
       outletNames - list of outlet assignments in order from outlet 1..4
    the first 3 are required, the last two have sensible defaults.

    If no config file is given, kwargs are used to set the parameters, of which
    addr, user, and pass are *required*

    If no config file or valid kwargs are given, we try a default configuration file
    in $HOME/.demonext/config/raritanPDU.txt as a last resort.

    If all else fails, fail out and gripe.
    """
    
    def __init__(self,*args,**kwargs):
 
        haveOutNames = False
        self.noCert = True
        self.pduInfo = {}

        # argument options from nothing, a config file, or individual keywords
        
        if len(args) > 0:
            cfgFile = args[0]

        elif len(kwargs) > 0:
            cfgFile = None
            for key, val in kwargs.items():
                if key.lower() == "ipaddr":
                    self.pduAddr = val
                elif key.lower() == "userid":
                    self.pduUser = val
                elif key.lower() == "passwd":
                    self.pduPass = val
                elif key.lower() == "nocert":
                    self.noCert = val
                elif key.lower() == "outlets":
                    self.outID = val
                    haveOutNames = True
                else:
                    raise ValueError(f"Unrecognized kwarg {key}, must be [ipaddr,userid,passwd,nocert,outlets]")
        
        else:
            # default config file
            cfgFile = str(Path.home() / ".demonext/config/raritanPDU.txt")

        if cfgFile is not None:
            if os.path.exists(cfgFile):
                with open(cfgFile,"r") as stream:
                    try:
                        config = yaml.safe_load(stream)
                    except yaml.YAMLError as exp:
                        raise RuntimeError(f"Cannot open runtime configuration file {cfgFile}: {exp}")

                self.pduInfo = config["pdu"]
            
                self.pduAddr = self.pduInfo["ipAddr"]
                self.pduUser = self.pduInfo["userID"]
                self.pduPass = self.pduInfo["passwd"]
            
                try:
                    self.noCert = self.pduInfo["disableCert"]
                except:
                    self.noCert = True

                try:
                    self.outID = self.pduInfo["outletNames"]
                    haveOutNames = True
                except:
                    haveOutNames = False
            
            else:
                raise RuntimeError(f"Runtime configuration file {cfgFile} does not exist")
        
        # Instantiate a Raritan RPC agent - this is the next fail-out point

        try:
            self.agent = rpc.Agent("http",self.pduAddr,self.pduUser,self.pduPass,
                                   disable_certificate_verification=self.noCert)
        except Exception as exp:
            raise RuntimeError(f"Could not open Raritan PDU RPC agent: {exp}")

        # we have an agent, get PDU model and peripheral device instances
        
        self.pdu = pdumodel.Pdu("/model/pdu/0",self.agent)
        self.pdm = peripheral.DeviceManager("/model/peripheraldevicemanager",self.agent)

        # PDU inlets

        self.inlets = self.pdu.getInlets()
        self.numInlets = len(self.inlets)
        if self.numInlets > 0:
            self.inletSensors = self.inlets[0].getSensors()
        else:
            self.inletSensors = None

        # PDU outlets

        self.outlets = self.pdu.getOutlets()
        self.numOutlets = len(self.outlets)
        if self.numOutlets > 0:
            self.outletNames = {}  # outlet name bindings dictionary
            if haveOutNames: # config file has outlet name assignments that override internal PDU names
                for i in range(self.numOutlets):
                    tempID = self.outID[i]
                    if len(tempID) > 0:
                        self.outletNames[tempID.lower()] = i + 1
                    else:
                        self.outletNames[f"Outlet{i+1}"] = i + 1
            else:
                self.outID = []     # use labels assigned to each outlet on the Raritan proper
                
            self.outDelay = []  # outlet power cycle delay in seconds
            self.outState = []  # outlet state sensor objects - query with .getState().value
            iOut = 0
            for outlet in self.outlets:
                iOut += 1
                outSet = outlet.getSettings()

                # no outlet names in the config file, get from the PDU
                
                if not haveOutNames:
                    tempID = outSet.name
                    if len(tempID) == 0:
                        tempID = f"outlet{iOut}"
                    self.outID.append(tempID)
                    self.outletNames[tempID.lower()]=iOut

                # outlet power cycle delay in seconds

                self.outDelay.append(outSet.cycleDelay)

                # outlet on/off sensors

                outSens = outlet.getSensors()
                self.outState.append(outSens.outletState)
                
        else:
            self.outID = None
            self.outDelay = None
            self.outState = None
                
        # PDU peripheral device slots - assume one temp/humidity sensor connected

        slots = self.pdm.getDeviceSlots()
        self.Temp = slots[0].getDevice() # peripheral temperature sensor device
        self.RH = slots[1].getDevice()   # peripheral humidity sensor device

        # Useful boolean translation dictionaries

        self.OnOff = {True:"On",False:"Off"}
        self.YesNo = {True:"Yes",False:"No"}
        
        
    # Methods


    def getInletData(self):
        """
        Reads the PDU inlet sensors and returns inletData dictionary with
        the data.  If a sensor read fails, reports -99.99 (not read) for
        value.

        Returns
        -------
        inletData : dict
            Dictionary with the inlet sensor data

        """
        inletData = {}
        try:
            inletData["voltage"] = self.inletSensors.voltage.getReading().value # V
        except:
            inletData["voltage"] = -99.99
        
        try:
            inletData["current"] = self.inletSensors.current.getReading().value # A
        except:
            inletData["current"] = -99.99

        try:
            inletData["peakCurrent"] = self.inletSensors.peakCurrent.getReading().value # A
        except:
            inletData["peakCurrent"] = -99.99

        try:
            inletData["power"] = self.inletSensors.activePower.getReading().value # W
        except:
            inletData["power"] = -99.99

        try:
            inletData["appPower"] = self.inletSensors.apparentPower.getReading().value # VA
        except:
            inletData["appPower"] = -99.99

        try:
            inletData["Energy"] = self.inletSensors.activeEnergy.getReading().value/1000.0 # convert to kWh
        except:
            inletData["Energy"] = -99.99

        try:
            inletData["lineFrequency"] = self.inletSensors.lineFrequency.getReading().value # Hz
        except:
            inletData["lineFrequency"] = -99.99

        return inletData


    def getInletFITS(self):
        """
        Reads the PDU inlet sensors and returns inletFITS dictionary with
        the data in FITS keyword/value pairs ready for inserting to an
        image FITS header.  
        
        If a sensor read fails, reports -99.99 (not read) for the value.

        Returns
        -------
        inletData : dict
            Dictionary with the inlet sensor data as FITS keyword/value pairs.

        """
        inletData = {}

        try:
            inletData["PDU_VAC"] = self.inletSensors.voltage.getReading().value
        except:
            inletData["PDU_VAC"] = -99.99
        
        try:
            inletData["PDU_AMPS"] = self.inletSensors.current.getReading().value
        except:
            inletData["PDU_AMPS"] = -99.99

        try:
            inletData["PDU_PEAK"] = self.inletSensors.peakCurrent.getReading().value
        except:
            inletData["PDU_PEAK"] = -99.99

        try:
            inletData["PDU_WATT"] = self.inletSensors.activePower.getReading().value
        except:
            inletData["PDU_WATT"] = -99.99

        try:
            inletData["PDU_VA"] = self.inletSensors.apparentPower.getReading().value
        except:
            inletData["PDU_VA"] = -99.99

        try:
            inletData["PDU_KWH"] = self.inletSensors.activeEnergy.getReading().value/1000.0 # convert to kWh
        except:
            inletData["PDU_KWH"] = -99.99

        try:
            inletData["PDU_FREQ"] = self.inletSensors.lineFrequency.getReading().value
        except:
            inletData["PDU_FREQ"] = -99.99

        return inletData

            
    """Read environmental sensors connected to the PDU

    
    """
    
    def getEnv(self):
        """
        Reads the peripheral temperature and humidity sensors, returns temperature in
        degrees C and relative humidity in percent relative humidity.  Returns -99.99
        if a sensor read fails.

        Returns
        -------
        airTemp : float
            air temperature in degrees C.
        airRH : float
            air relative humidity in percent (%).

        """
        try:
            airTemp = self.Temp.device.getReading().value
        except:
            airTemp = -99.99

        try:
            airRH = self.RH.device.getReading().value
        except:
            airRH = -99.99
            
        return airTemp, airRH


    def getEnvFITS(self):
        """
        Reads the peripheral temperature and humidity sensors, 
        and returns A FITS header dictionary with PDU_TEMP and 
        PDU_RH as FITS-ready keyword/value pairs.  
        
        Values are set to -99.99 if sensor reads fail

        Returns
        -------
        pduEnv : dict
            Dictionary with the air temperaure and relative humidity in FITS-ready format.

        """
        pduEnv = {}
        try:
            pduEnv["PDU_TEMP"] = self.Temp.device.getReading().value
        except:
            pduEnv["PDU_TEMP"] = -99.99

        try:
            pduEnv["PDU_RH"] = self.RH.device.getReading().value
        except:
            pduEnv["PDU_RH"] = -99.99
            
        return pduEnv
        
    
    def getTemp(self):
        """
        Returns the PDU peripheral temperature sensor reading in degrees C 
        or -99.99 if sensor read failed

        Returns
        -------
        airTemp : float
            Air temperature in degrees C.

        """
        try:
            airTemp = self.Temp.device.getReading().value
        except:
            airTemp = -99.99
        return airTemp


    def getRH(self):
        """
        Returns the PDU peripheral relative humidity sensor reading in percent
        or -99.99 if sensor read failed

        Returns
        -------
        airRH : float
            air relative humidity in percent (%).

        """
        try:
            airRH = self.RH.device.getReading().value
        except:
            airRH = -99.99
        return airRH


    def getOutlet(self,iOut):
        """
        Get the power status of an outlet by number

        Parameters
        ----------
        iOut : int
            Number of the outlet to read, 1..numOutlets

        Raises
        ------
        ValueError
            if iOut is not in the range 1..numOutlets.
        RuntimeError
            if the outlet state could not be read

        Returns
        -------
        bool
            True if outlet power is On, False if outlet power is Off.

        """
        
        if iOut < 1 or iOut > self.numOutlets:
            raise ValueError(f"Outlet out of range, must be 1..{self.numOutets}")

        try:
            status = self.outState[iOut-1].getState().value
            if status:
                return True
            else:
                return False
        except Exception as exp:
            raise RuntimeError(f"Could not read state of outlet {iOut}: {exp}")
        

    def setOutlet(self,iOut,turnOn):
        """
        Set the numbered outlet on or off.  Tests the state after the
        command to verify if on or off.

        Parameters
        ----------
        iOut : integer
            number of the outlet to set, 1..numOutlets
        turnOn : bool
            True to turn outlet ON, False to turn OFF

        Raises
        ------
        ValueError
            if iOut is out of range 1..numOutlets
        RuntimeError
            if the outlet state cannot be changed

        Returns
        -------
        bool
            True if the outlet is ON, False if the outlet is OFF.

        """
        if iOut < 1 or iOut > self.numOutlets:
            raise ValueError(f"Outlet out of range, must be 1..{self.numOutets}")

        outlet = self.outlets[iOut-1]

        if turnOn:
            try:
                outlet.setPowerState(outlet.PowerState.PS_ON)
            except Exception as exp:
                raise RuntimeError(f"Could not set outlet {iOut} power ON: {exp}")
        else:
            try:
                outlet.setPowerState(outlet.PowerState.PS_OFF)
            except Exception as exp:
                raise RuntimeError(f"Could not set outlet {iOut} power OFF: {exp}")
                
        time.sleep(1)
        try:
            status = self.outState[iOut-1].getState().value
            if status:
                return True
            else:
                return False
        except Exception as exp:
            raise RuntimeError(f"Could not read power state of outlet {iOut}: {exp}")
        

    def outletStates(self):
        """
        Return a list of booleans with the power state for all outlets
        on the PDU.  True = outlet ON, False = outlet OFF.

        Raises
        ------
        RuntimeError
            if it could not read one or more oulets states.

        Returns
        -------
        states : boolean list
            List of True/False of the state of each outlet.

        """
        states = []
        for iOut in range(self.numOutlets):
            try:
                status = self.outState[iOut-1].getState().value
                if status:
                    states.append(True)
                else:
                    states.append(False)
            except Exception as exp:
                raise RuntimeError(f"Could not read power state of outlet {iOut+1}: {exp}")
                states = []
                
        return states

    # Higher-level functions
    

    def setPower(self,outletName,action):
        """
        Set the power state of a named outlet.

        Parameters
        ----------
        outletName : string
            Name of the outlet to set.
        action : string
            Action to take, one of "on", "off", or "cycle"

        Raises
        ------
        ValueError
            if the outlet name is not recognized.
        RuntimeError
            if the outlet state cannot be changed or queried.

        Returns
        -------
        boolean
            Outlet state after the action requested, True=ON, False=OFF

        """
        outID = outletName.lower()
        if outID not in self.outletNames:
            raise ValueError(f"{outletName} is not a known outlet name")
        iOut = self.outletNames[outID]

        act = action.lower()
        if act not in ['on','off','cycle']:
            raise ValueError(f"{act} is not a recognized action, must be one of on/off/cycle")
         
        if act in ['on','off']:
            try:
                return self.setOutlet(iOut,act=='on')
            except Exception as exp:
                raise RuntimeError(f"Could not power {outletName} {action}: {exp}")
        else:
            # power cycle
            try:
                self.outlets[iOut-1].cyclePowerState()
                time.sleep(self.outDelay[iOut-1]+1) # wait cycle delay + 1 second
                return self.getOutlet(iOut)
            except Exception as exp:
                raise RuntimeError(f"Could not power cycle {outletName}: {exp}")                
            

    def isOutletOn(self,outletName):
        """
        Is the named outlet powered on?

        Parameters
        ----------
        outletName : string
            Name of the outlet to test.

        Raises
        ------
        ValueError
            raised if the outletName is not recognized.
        RuntimeError
            raised if the outlet state cannot be read.

        Returns
        -------
        boolean
            True if outlet is ON, False if outlet is OFF.

        """
        outID = outletName.lower()
        if outID not in self.outletNames:
            raise ValueError(f"{outletName} is not a known outlet name")
        try:
            return self.getOutlet(self.outletNames[outID])
        except Exception as exp:
            raise RuntimeError(f"Could not read {outletName} outlet state: {exp}")


    # Formatted printing functions

    
    def printOutletInfo(self):
        """
        Prints a formatted table of the current status of all outlets.

        Returns
        -------
        None.

        """
        print("\nRaritan PDU outlet status:")
        for i in range(self.numOutlets):
            outID = self.outID[i]
            delay = self.outDelay[i]
            outlet = self.outlets[i]
            try:
                outOnOff = self.OnOff[self.outState[i].getState().value]
            except:
                outOnOff = "??"

            if outlet.getSettings().startupState == pdumodel.Outlet.StartupState.SS_ON:
                defOnOff = "ON"
            else:
                defOnOff = "OFF"
            print(f"  Outlet {i+1}: {outID}")
            print(f"          Power: {outOnOff}")
            print(f"        Startup: {defOnOff}")
            print(f"    Cycle Delay: {delay} seconds\n")


    def printOutlets(self):
        """
        Prints a formatted table of the named outlets

        Returns
        -------
        None.

        """
        print(f"\nThere are {len(self.outletNames)} named PDU outlets:")
        for key in self.outletNames:
            print(f"  Outlet {self.outletNames[key]}: {key}")

    
    def printMetaData(self):
        """
        Prints a summary of the PDU metdata

        Raises
        ------
        RuntimeError
            raised if cannot retrieve PDU metadata.

        Returns
        -------
        None.

        """
        try:
            md = self.inlets[0].getMetaData()
        except Exception as exp:
            raise RuntimeError(f"Could not retrieve PDU metadata: {exp}")

        print("\nRaritan PDU inlet metadata:")
        print(md)


    def printInletData(self):
        """
        Prints a summary table of PDU inlet sensor readings of interest.

        Raises
        ------
        RuntimeError
            raised if it cannot read PDU inlet sensors.

        Returns
        -------
        None.

        """
        try:
            rmsV = self.inletSensors.voltage.getReading().value
            freq = self.inletSensors.lineFrequency.getReading().value
            rmsI = self.inletSensors.current.getReading().value
            peakI = self.inletSensors.peakCurrent.getReading().value
            power = self.inletSensors.current.getReading().value
            VA = self.inletSensors.apparentPower.getReading().value
            kWh = self.inletSensors.activeEnergy.getReading().value/1000.0 # conver to kWh
        except Exception as exp:
            raise RuntimeError(f"Could not read PDU inlet sensor data: {exp}")
            
        print("\nRaritan PDU Inlet Sensors:")
        print(f"    RMS Voltage: {rmsV:.2f} VAC, {freq:.2f} Hz")
        print(f"    RMS Current: {rmsI:.3f} A, {peakI:.3f} A peak")
        print(f"          Power: {power:.2f} W")
        print(f"  Active Energy: {kWh:.2f} kWh")
        print(f" Apparent Power: {VA:.1f} VA")


    def printEnv(self):
        """
        Print a summary of the PDU peripheral temperature and humidity
        sensors. 

        Raises
        ------
        RuntimeError
            raised if the peripheral sensors cannot be read.

        Returns
        -------
        None.

        """
        
        try:
            temp,rh = self.getEnv()
        except Exception as exp:
            raise RuntimeError(f"Could not read PDU environmental sensor data: {exp}")
        
        print("\nRaritan PDU peripheral sensors:")
        print(f"  Temperature: {temp:.2f}C")
        print(f"     Humidity: {rh:.2f}%")

    
