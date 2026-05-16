#!/usr/bin/env python
"""
pduInletStats - read status from a Raritan PDU

Usage:
   pduInletStats

Description
   This program uses an instance of the raritanPDU class to communicate
   with a Raritan PDU via the JSON-RPC API python client bindings to
   retrieve inlet data for a given time interval and then compute
   and display summary statistics (mean, median, stdev)

Author
   R. Pogge, OSU Astronomy Department
   pogge.1@osu.edu
   2024 Dec 10

Modification History:
   2024 Dec 10 - uses the raritanPDU class [rwp/osu]

"""

import sys
import time
import numpy as np

# Custom Raritan PDU interface class

import raritanPDU

# path handling

from pathlib import Path

# Version info

verName = "pduInletStats v1.0.3"
verDate = "2024-12-12"

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

# sample data, accumulate arrays, and compute stats

numSamples = 120 # about 1 minute at typical max sampling rate

voltage = []
current = []
power = []
appP = []

t0 = time.time()
for i in range(numSamples):
    try:
        inData = pdu.getInletData()
        voltage.append(inData['voltage'])
        current.append(inData['current'])
        power.append(inData['power'])
        appP.append(inData['appPower'])
        dt = time.time()-t0
        sys.stdout.write(f"\rReading PDU Sample {i+1}: {dt:.1f}s {inData['voltage']:6.2f}V {inData['current']:6.3f}A {inData['power']:6.2f}W {inData['appPower']:6.2f}VA")
        sys.stdout.flush()
        
    except Exception as exp:
        print(f"missed reading {i}: {exp}")
    
# done, stats

tSamp = time.time() - t0
print(f"\nPDU Inlet Usage Stats:")
print(f"  NumSamples = {numSamples} for {tSamp:.2f} seconds ({tSamp/60.0:.2f} minutes)\n")
print(f"  Measure   Mean    Median    RMS      Min      Max")
print(f"  Voltage {np.mean(voltage):6.2f}V  {np.median(voltage):6.2f}V  {np.std(voltage):6.2f}V  {np.min(voltage):6.2f}V  {np.max(voltage):6.2f}V")
print(f"  Current {np.mean(current):6.3f}A  {np.median(current):6.3f}A  {np.std(current):6.3f}A  {np.min(current):6.3f}A  {np.max(current):6.3f}A")
print(f"    Power {np.mean(power):6.2f}W  {np.median(power):6.2f}W  {np.std(power):6.2f}W  {np.min(power):6.2f}W  {np.max(power):6.2f}W")
print(f" AppPower {np.mean(appP):6.2f}VA {np.median(appP):6.2f}VA {np.std(appP):6.2f}VA {np.min(appP):6.2f}VA {np.max(appP):6.2f}VA\n")

sys.exit(0)
