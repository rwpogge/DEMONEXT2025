#!/usr/bin/env python
"""
outletOnOff - outlet on/off/cycle test

Usage:
   outletOnOff

Description
   This program uses an instance of the raritanPDU class to communicate
   with a Raritan PDU via the JSON-RPC API python client bindings and
   retrieve relevant status information.

   We hard code the outlet to control for the test. Outlets are
   numbered 1 though 4 on this unit.  Beware: don't test outlet 1
   as that is the one the DEMONEXT PC is connected to (we should not test
   seppuku mode unless we mean it, or do test it from a computer that
   is not connected to outlet 1).

Author
   R. Pogge, OSU Astronomy Department
   pogge.1@osu.edu
   2024 Dec 9 

Modification History:
   2024 Dec 09 - uses the raritanPDU class [rwp/osu]
   2024 Dec 10 - uses new raritanPDU class with runtime config file [rwp/osu]
 
"""

import sys
import time

from pathlib import Path

# Custom Raritan PDU interface class

import raritanPDU

# Version info

verName = "outletOnOff v1.0.3"
verDate = "2024-12-11"

# On/Off convenience dictionary

OnOff = {True:"On",False:"Off"}

# Runtime configuration file with the Raritan PDU setup info

cfgFile = "raritanPDU.txt" # local file

#cfgFile = str(Path.home() / "Documents/Config/demonext.txt") # windows 10 config

#cfgFile = str(Path.home() / ".demonext/config/demonext.txt") # linux test config

# Instantiate a raritanPDU instance

try:
    pdu = raritanPDU.raritanPDU(cfgFile)
except Exception as exp:
    print(f"ERROR: raritanPDU() init returned {exp}")
    sys.exit(1)
    
# Retrieve outlet name list

pdu.printOutlets()

# Test the low-level setOutlet() method to control outlets by number 1..4 and boolean

testOut = 4 # test on outlet 4
powerOn = True # T=On, F=Off

try:
    status = pdu.getOutlet(testOut)
    print(f"\nBefore: outlet {testOut} is {OnOff[status]}")
except Exception as exp:
    print(f"ERROR: outlet {testOut} query fault: {exp}")
    
print(f"  Turning outlet {testOut} {OnOff[powerOn]}...")
try:
    status = pdu.setOutlet(testOut,powerOn)
    print(f"After: outlet {testOut} {OnOff[status]}")
except Exception as exp:
    print(f"ERROR: outlet {testOut} fault: {exp}")

# Test the high-level setPower() method to control outlets by name and action

outName = "Aux"  # names and actions are case-insensitive
action = "off"

try:
    print(f"\nBefore: {outName} outlet is {OnOff[pdu.isOutletOn(outName)]}")
except Exception as exp:
    print(f"ERROR: {exp}")

if action in ['on','off']:
    print(f"  Turning {outName} outlet {action}...")
else:
    print(f"  Power Cycling {outName}...")

try:
    status = pdu.setPower(outName,action)
    print(f"After: {outName} outlet is {OnOff[status]}")
except Exception as exp:
    print(f"Error: {outName} outlet {action} not done: {exp}")

sys.exit(0)
