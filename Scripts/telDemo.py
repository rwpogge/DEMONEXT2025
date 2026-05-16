"""telDemo - demo program for the demonext telescope class

Demo program used to check the telescope control componets
of the demonext module.

Author:
  R. Pogge, OSU Astronomy Dept.
  pogge.1@osu.edu
  2024 Dec 20

Modification History:
  2024 Dec 20 - first version, demonext with config and telescope, live test [rwp/osu]
  2024 Dec 27 - added slewToRADec() testing, and RA/Dec validation testing [rwp/osu]
"""

import os
import sys

# pathlib for path handling

from pathlib import Path

# logging for runtime logging

import logging

# custom demonext module

import demonext
from demonext import config, telescope

# useful boolean translation methods

YesNo = {True:"Yes",False:"No"}
OnOff = {True:"On",False:"Off"}

# default configuration file directory

configDir = Path.home() / ".demonext/config" # relative to home
defaultCfg = "demonext.txt"

#
# -- sloppy main
#

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
    print("Usage: telDemo [cfgFile]")
    sys.exit(0)

# instantiate a Config instance as "cfg" for configuration the main
# runtime configuration file

try:
    cfg = config.Config(cfgFile)
except Exception as exp:
    print(f"ERROR: (Config): {exp}")
    sys.exit(1)

# start logging

logDir = demonext.homePath(cfg.config["directories"]["LogDir"])

logFile = str(Path(logDir) / f"eng{demonext.obsDate()}.txt")

logging.basicConfig(filename=logFile,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                    filemode="a",
                    level=logging.INFO)

logger = logging.getLogger("telDemo")

logger.info("Started telDemo")

# instantiate a telescope instance

try:
    tel = telescope.Telescope(cfgFile)
except Exception as exp:
    print(f"ERROR: {exp}")
    sys.exit(1)

# connect to the telescope controller

try:
    tel.connect()
except Exception as exp:
    print(f"Cannot connect: {exp}")

if tel.connected:
    print(f"Connected to {tel.telName} successfully")
else:
    print(f"Failed to connect to {tel.telName}")

if tel.isTracking():
    tel.Tracking("off")

# start simple, query information only, no moves yet

telInfo = tel.position()

print("\nTelescope Position:")
print(f"  Alt/Az: {telInfo['Alt']:.5f} d, {telInfo['Az']:.5f} d")
print(f"  RA/Dec: {telInfo['RA']:.5f} h, {telInfo['Dec']:.5f} d")
print(f"  LST/HA: {telInfo['LST']:.5f}h, {telInfo['HA']:.5f} h")
print(f"    SecZ: {telInfo['SecZ']:.2f}")

print(f"\nTelescope HA={tel.HA():.2f}h")
print(f"        SecZ={tel.SecZ():.2f}")

print("\nTelescope Mount Status:")
print(f"   At Home? {YesNo[tel.isHome()]}")
print(f"    Parked? {YesNo[tel.isParked()]}")
print(f"  Tracking: {OnOff[tel.isTracking()]}")
print(f"   Slewing? {YesNo[tel.isSlewing()]}")

# Now get frisky - move the telescope

# do only 1 at a time, please

doHome = False
doPark = True
doAltAz = False
doRADec = False

# limits

print("\nPointing Limits:")
print(f"   HA: {tel.minHA:.1f} to {tel.maxHA:.1f}h")
print(f"  Dec: {tel.minDec:.2f} to 0 d")
print(f"  Alt: {tel.minAlt:.1f} to 90 d")

# try the RADec validator

reqRA = 18.0 # hours
reqDec = 0.2 # degrees

if tel.isRADecValid(reqRA,reqDec):
    print("RA/Dec valid")
else:
    print(f"RA/Dec invalid: {tel.msg}")

# activities

if doHome:
    print("\nHoming the telescope...")
    tel.Home()
    if tel.isHome():
        telInfo = tel.position()
        print(f"Done: Telescope at Home: Alt={telInfo['Alt']:.5f}d Az={telInfo['Az']:.5f}d, tracking {OnOff[tel.isTracking()]}")
    else:
        telInfo = tel.position()
        print(f"Warning: Telescope not at Home: Alt={telInfo['Alt']:.5f}d Az={telInfo['Az']:.5f}d, tracking {OnOff[tel.isTracking()]}")

if doPark:
    print("\nParking the telescope...")
    tel.Park()
    if tel.isParked():
        telInfo = tel.position()
        print(f"Done: Telescope is Parked: Alt={telInfo['Alt']:.5f}d Az={telInfo['Az']:.5f}d, tracking {OnOff[tel.isTracking()]}")
    else:
        telInfo = tel.position()
        print(f"Done: Telescope says not Parked: Alt={telInfo['Alt']:.5f}d Az={telInfo['Az']:.5f}d, tracking {OnOff[tel.isTracking()]}")

if doAltAz:
    reqAlt = 15.0
    reqAz = 180.0
    print(f"\nMoving telescope to Alt={reqAlt:.2f}d Az={reqAz:.2f}d...")
    tel.Tracking("on")
    print(f"  Sidereal tracking is {OnOff[tel.isTracking()]}")
    tel.slewToAltAz(reqAlt,reqAz)
    telInfo = tel.position()
    dAlt = reqAlt - telInfo['Alt']
    dAz = reqAz - telInfo['Az']
    print(f"Done: Telescope at Alt={telInfo['Alt']:.5f}d Az={telInfo['Az']:.5f}d, tracking {OnOff[tel.isTracking()]}")
    print(f"      offset: dAlt={3600*dAlt:.2f}arcsec dAz={3600*dAz:.2f}arcsec")

if doRADec:
    print(f"\nMoving telescope to RA={reqRA:.3f}h Dec={reqDec:.3f}d...")
    tel.Tracking("on")
    tel.slewToRADec(reqRA,reqDec)
    telInfo = tel.position()
    print(f"Done: Telescope at RA={telInfo['RA']:.5f}h Dec={telInfo['Dec']:.5f}d, tracking {OnOff[tel.isTracking()]}")
    

# all done

if tel.isTracking():
    tel.Tracking("Off")

logger.info("telDemo done")

sys.exit(0)
