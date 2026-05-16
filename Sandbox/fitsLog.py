#!/usr/bin/env python
"""
fitsLog - make a FITS data log

Usage: fitsLog

Creates 00Index.txt in the current working directory

R. Pogge, OSU Astronomy
pogge.1@osu.edu
2025 Jan 13
"""

import sys
import glob

# fast FITS header access:

from astropy.io.fits import getheader

# pandas

import pandas as pd
import numpy as np

# throttle nuisance warnings

import warnings
warnings.filterwarnings("ignore",category=UserWarning, append=True)
warnings.filterwarnings("ignore",category=RuntimeWarning, append=True)

# Hard coded MODS logging info

fitsKeys = ["PRGRM_ID","IMAGETYP","OBJECT","OBJCTRA","OBJCTDEC","EXPTIME","DATE-OBS",
            "AIRMASS","FILTER","NAXIS1","NAXIS2","FILENAME"]

keyFmts = ["12.12s","15.15s","15.15s","11.11s","11.11s","6.1f","21.21s","5.2f","7.7s","4d","4d","36.36s"]

tabHeads = ["ProjectID","ImgTyp","Object","RA","Dec","Exp","UTCDate/Time","SecZ","Filter","numX","numY","Filename"]

tabFmts = ["12.12s","15.15s","15.15s","11.11s","11.11s","6.6s","21.21s","5.5s","7.7s","4.4s","4.4s","36.36s"]

# Get a list of all FITS data matching pattern

fitsFiles = glob.glob("*.fits")

if len(fitsFiles) == 0:
    print("No FITS files in this directory, no log created.")
    sys.exit(1)

fileList = sorted(fitsFiles)

# start the FITS log

logFile = "00Index.txt"

ml = open(logFile,"w")

# log header

hdrStr = ""
for i in range(len(tabHeads)):
    hdrStr += f"{tabHeads[i]:{tabFmts[i]}} "

ml.write(f"{hdrStr}\n")

# log data are stored as a dictionary of lists for easy sorting

logData = {}
for key in fitsKeys:
    logData[key] = []

# populate the logData dictionary

for fitsFile in fileList:
    hdr = getheader(fitsFile)

    for i in range(len(fitsKeys)):
        key = fitsKeys[i]
        fmt = keyFmts[i]
        tab = tabFmts[i]
        
        if key == "FILENAME":
            logData[key].append(f"{fitsFile:{fmt}}")
            
        else:
            try:
                keyData = hdr[key]
            except:
                keyData = ""

            try:
                logData[key].append(f"{keyData:{fmt}}")
            except:
                logData[key].append(f"{keyData:{tab}}")

# Sort the data records by DATE-OBS

sortList = np.argsort(logData["DATE-OBS"])

# Export into logFile

for i in range(len(fileList)):
    outStr = ""
    iData = sortList[i]
    for j in range(len(fitsKeys)):
        key = fitsKeys[j]
        tab = tabFmts[j]

        outStr += f"{logData[key][iData]:{tab}} "
        
    ml.write(f"{outStr}\n")

# all done!

ml.close()
print(f"Done: wrote {len(fitsFiles)} records to {logFile}")

sys.exit(0)
