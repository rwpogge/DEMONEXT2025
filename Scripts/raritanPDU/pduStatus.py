#!/usr/bin/env python
"""
pduStatus - read status from a Raritan PDU

Usage:
   pduStatus

Description
   This program uses an instance of the raritanPDU class to communicate
   with a Raritan PDU via the JSON-RPC API python client bindings and
   retrieve relevant status information.  Mostly minimally or un-formatted
   data dump to test the interface, we need something better for regular
   use.

Author
   R. Pogge, OSU Astronomy Department
   pogge.1@osu.edu
   2024 Dec 9 

Modification History:
   2024 Dec 9 - uses the raritanPDU class [rwp/osu]

"""

import sys

# Custom Raritan PDU interface class

import raritanPDU

# path handling

from pathlib import Path

# Version info

verName = "pduStatus v1.0.3"
verDate = "2024-12-11"

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

try:
    pdu.printMetaData()
    pdu.printInletData()
    pdu.printOutletInfo()
    pdu.printEnv()
    pdu.printOutlets()

    # try the variations on inlet data handling

    print("\ngetInletData():")
    id = pdu.getInletData()
    print(id)

    print("\ngetInletFITS():")
    id = pdu.getInletFITS()
    print(id)
    
    print("\ngetEnvFITS():")
    id = pdu.getEnvFITS()
    print(id)

    print("\noutletNames dictionary:")
    print(pdu.outletNames)

    
    print("\npduInfo dictionary:")
    try:
       print(pdu.pduInfo)
    except:
       print("  none")
       
except Exception as exp:
    print(f"**ERROR: {exp}")
    sys.exit(1)

sys.exit(0)
