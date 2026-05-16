"""dxDemo - demo program for the demonext module

Demo program used to check the various components of
the demonext module.

Author:
  R. Pogge, OSU Astronomy Dept.
  pogge.1@osu.edu
  2024 Dec 14

Modification History:
  2024 Dec 14 - first version, demonext with config and pdu [rwp/osu]
  2024 Dec 18 - added logging, many bug fixes and improvements [rwp/osu]
"""

import os
import sys

# pathlib for path handling

from pathlib import Path

# logging for runtime logging

import logging

# custom demonext module

import demonext
from demonext import config, pdu

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
    print("Usage: dxDemo [cfgFile]")
    sys.exit(0)

# instantiate a Config instance as "cfg" for configuration the main
# runtime configuration file

try:
    cfg = config.Config(cfgFile)
except Exception as exp:
    print(f"ERROR: (Config): {exp}")
    sys.exit(1)

# list of dictionaries in cfgFile

print(f"\ndictionaries in {cfgFile}: {cfg.dicts}")

cfg.print()

# start logging

logDir = demonext.homePath(cfg.config["directories"]["LogDir"])

logFile = str(Path(logDir) / f"eng{demonext.obsDate()}.txt")

logging.basicConfig(filename=logFile,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                    filemode="a",
                    level=logging.INFO)

logger = logging.getLogger("dxDemo")

logger.info("Started dxDemo")

# retrieve the pdu config dictionary from the config file

try:
    pduInfo = cfg.config["pdu"]
except Exception as exp:
    print(f"ERROR: {exp}")
    sys.exit(1)

# instantiate a Raritan PDU interface instance as "power" for AC power
# control using the runtime configuration file given as the "config"
# entry in pduInfo.  Paths are relative to home, but might be absolute.

try:
    pdu = pdu.RaritanPDU(demonext.homePath(pduInfo["config"]))
except Exception as exp:
    print(f"ERROR: {exp}")
    sys.exit(1)

pdu.printInlet()
pdu.printOutlets()
pdu.printEnv()

# try switching on outlet 4 (aux - nothing connected!)

outlet = "aux"

print(f"\nPDU {outlet} outlet is {pdu.OnOff[pdu.isOn(outlet)]}")

print(f"Switching {outlet} ON...")
pdu.switch(outlet,"on")

print(f"\nPDU {outlet} outlet is {pdu.OnOff[pdu.isOn(outlet)]}")

print(f"Power cycling {outlet} power (cycle delay = 10s)")
pdu.cycle(outlet)

print(f"PDU {outlet} outlet is {pdu.OnOff[pdu.isOn(outlet)]}")

logger.info("dxDemo done")

sys.exit(0)
