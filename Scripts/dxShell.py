"""dxShell - interactive command-line shell for DEMONEXT

Interactive command-line interface (CLI) for operating the DEMONEXT remote
observatory system.

Author:
  R. Pogge, OSU Astronomy Dept.
  pogge.1@osu.edu
  2026 April 5

Modification History:
  2026 Apr 05 - first version, after SRO installation [rwp/osu]

"""

import sys
import os
import time
import math
import glob
import datetime
from datetime import date, timedelta

# Windows Component Object Model (COM) client module.

from win32com.client import Dispatch

# modules we need from anaconda

import numpy as np

# FITS writing and handling

from astropy.io import fits

# astropy units, time, and coordinate functions go here

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.coordinates import TETE
from astropy.time import Time

# we use pathlib for platform-agnostic path handling 

from pathlib import Path

# we use YAML for runtime configuration files

import yaml

# We use logging for runtime logs

import logging

# demonext module

import demonext
from demonext import config, pdu, camera, telescope, site, focuser, obsfile

# Boolean state convenience translation dictionaries

OnOff = {True:'On',False:'Off'}
YesNo = {True:'Yes',False:'No'}

# Windows system process list function

def getProcList():
    from win32com.client import GetObject
    wmi = GetObject("winmgmts:")
    procs = wmi.InstancesOf("win32_process") 
    procList = []
    for proc in procs:
        procList.append(proc.Name)
    return procList


#--------------------------------------------------------------------
#
# command functions
#

# total work in progress, this is just the barest scaffolding


def setPower(arg):
    return

def getPower(arg):
    return

def startProc(procID):
    return

def stopProc(procID):
    return

def showProc():
    return

def connectSys(sysID):
    return

def disconnectSys(sysID):
    return

def status():
    return

def setFilter(filtID):
    return

def getFilter(filtID):
    return

def siteInfo():
    return

def setFocus(foc):
    return

def stepFocus(dfoc):
    return

def getFocus():
    return

def guider(expTime,numExp):
    return

def setExp(expTime):
    return

def getExp(expTime):
    return

def setObject(objectID):
    return

def getObject():
    return

def setImgType(imType):
    return

def getImgType():
    return

def science(expTime,numExp):
    return

def setTelescope(args):
    return

def getTelescope(args):
    return


#--------------------------------------------------------------------
#
# main program
#

#
# -- sloppy main
#

# platform-agnostic path definition relative to home

configDir = Path.home() / ".demonext/config"
defaultCfg = "demonext.txt"

# command-line arguments on startup - very limited

if len(sys.argv)-1 == 0:
    cfgFile = str(Path() / configDir / defaultCfg)
elif len(sys.argv)-1 == 1:
    cfgFile = sys.argv[1]
    if not os.path.exists(cfgFile):
        # try adding the default configuration path
        cfgFile = str(configDir / sys.argv[1])
        if not os.path.exists(cfgFile):
            print(f"ERROR: could not find {cfgFile} in pwd or {str(configDir)}")
            sys.exit(1)
else:
    print("Usage: dxShell [cfgFile]")
    sys.exit(0)

# Startup bits

# instantiating a demonext Config class

try:
    cfg = config.Config(cfgFile)
except Exception as exp:
    print(f"ERROR: (Config) - {exp}")
    sys.exit(1)
    
# Start the runtime logger

logDir = demonext.homePath(cfg.config["directories"]["LogDir"])

logFile = str(Path(logDir) / f"eng{demonext.obsDate()}.txt")

logging.basicConfig(filename=logFile,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                    filemode="a",
                    level=logging.INFO)

# ID for log entries

logger = logging.getLogger("dxShell")

logger.info("Started the DEMONEXT interactive command shell")

# instantiate DEMONEXT classes we need

# Camera class 

try:
    cam = camera.Camera(cfgFile)
    print("Camera class started")
except Exception as exp:
    msg = f"Cannot initialize Camera instance: {exp}"
    print(f"ERROR: {msg}")
    logger.exception(msg)

# Telescope class

try:
    tel = telescope.Telescope(cfgFile)
    print("Telescope class started")
except Exception as exp:
    msg = f"Cannot initialize Telescope instance: {exp}"
    print(f"ERROR: {msg}")
    logger.exception(msg)

# Focuser class

try:
    foc = focuser.Focuser(cfgFile)
    print("Focuser class started")
except Exception as exp:
    msg = f"Cannot initialize Focuser instance: {exp}"
    print(f"ERROR: {msg}")
    logger.exception(msg)

# Site class

try:
    sro = site.Site(cfgFile)
    print("Site class started")
except Exception as exp:
    msg = f"Cannot initialize a Site instance: {exp}"
    print(f"ERROR: {msg}")
    logger.exception(msg)

# AC power control, the Raritan PDU has its own configuration file

try:
    pduInfo = cfg.config["pdu"]
except Exception as exp:
    print(f"ERROR: {exp}")

try:
    pdu = pdu.RaritanPDU(demonext.homePath(pduInfo["config"]))
    print("Connected to the DEMONEXT PDU")
except Exception as exp:
    print(f"ERROR: {exp}")

# DEMONEXT apps we need in order of startup

appList = ["SitechExe.exe","MaxIm_DL.exe","PWI3.exe"]

# list of all processes running on the system

procList = demonext.procList()

# Report on which processes are running before startup

print("Pre-startup observatory app status:")
for app in appList:
    if app in procList:
        print(f"  {app} is running")
    else:
        print(f"  {app} is not running")

# Start the command interpreter loop.

sys.exit(0)
