import os
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

import astropy.units as u

# we use pathlib for platform-agnostic path handling 

from pathlib import Path

# we use YAML for runtime configuration files

import yaml

# We use logging for runtime logs

import logging

# demonext

import demonext
from demonext import config, pdu

# socket and select for the server/client interaction

import socket
import select

# Initialize ASCOM objects

SiTech = None
MaxIm = None
MaxCam = None
Focuser = None
AutoFoc = None

# functions

# Boolean state convenience translation dictionaries

OnOff = {True:'On',False:'Off'}
YesNo = {True:'Yes',False:'No'}

# command reply

def cmdReply(msgType,cmdWord,msgStr,source,sock,remAddr):
    if source is sys.stdin:
        print(f"{msgType.upper()}: {cmdWord.upper()} {msgStr}")
    elif source is sock:
        replyStr = f"{msgType.upper()}: {cmdWord.upper()} {msgStr}"
        print(f"{remAddr[0]}:{remAddr[1]}>> {replyStr}")
        sock.sendto(replyStr.encode("utf-8"),remAddr)

    return

#-----------------------------------
#
# Runtime configuration
#

# platform-agnostic path definition relative to home

configDir = Path.home() / ".demonext/config"
configFile = "demonext.txt"

cfgFile = str(Path.home() / configDir / configFile)

# read by instantiating a demonext Config class

try:
    cfg = config.Config(cfgFile)
except Exception as exp:
    print(f"ERROR: (Config) - {exp}")

# default server is on port 10501 - eventually get these from the config file

udpAddr = "127.0.0.1"
udpPort = 10501
timeout = 60.0 # housekeeping timeout in seconds

# debug flag

debug = False

#-----------------------------------
#
# Logging services
#

# start the logger

logDir = demonext.homePath(cfg.config["directories"]["LogDir"])

logFile = str(Path(logDir) / f"eng{demonext.obsDate()}.txt")

logging.basicConfig(filename=logFile,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                    filemode="a",
                    level=logging.INFO)

# ID for our log entries is "server"

logger = logging.getLogger("server")

msg = "Started the DEMONEXT server"
logger.info(msg)
print(msg)

#-----------------------------------
#
# PDU services
#

# retrieve the PDU config dictionary from the config file

try:
    pduInfo = cfg.config["pdu"]
except Exception as exp:
    print(f"ERROR: {exp}")

# Instantiate a Raritan PDU interface instance as "power" for AC power
# control using the runtime configuration file given as the "config"
# entry in pduInfo.  Paths are relative to home, but might be absolute.

try:
    pdu = pdu.RaritanPDU(demonext.homePath(pduInfo["config"]))
    print("Connected to the DEMONEXT PDU")
except Exception as exp:
    print(f"ERROR: {exp}")

print(f"{remAddr[0]}:{remAddr[1]}>> {msgStr}")

# outlets we use on the PDU

pduOutlets = ['CCD','Telescope']

def outletStatus(outlets):
    outletDict = {}
    for outlet in outlets:
        outletDict[outlet] = pdu.OnOff[pdu.isOn(outlet)]
    return outletStatus

#-----------------------------------
#
# Runtime processes we control
#

# DEMONEXT apps we need in order of startup

appList = ["SitechExe.exe","MaxIm_DL.exe","PWI3.exe"]

def procStatus(appList):
    procDict = {}
    procList = demonext.procList()
    for app in appList:
        if app in procList:
            procDict[app] = "Running"
        else:
            procDict[app] = "Stopped"

    return procDict


def startSTI(stiExe="SitechExe.exe"):
    #
    # full path to the SitechExe.exe executable.  Use if not yet in the Windows PATH
    #
    # stiExe = r"C:\Program Files (x86)\Common Files\ASCOM\Telescope\SiTech\SitechExe.exe"
    #
    # short version if we have installed the observatory apps in the Window PATH
    #
    
    procList = demonext.procList()

    if stiExe in procList:
        continue # already running...
    else:
        try:
            os.startfile(stiExe)
            time.sleep(5)
        except Exception as exp:
            msg = f"Cannot start {stiExe}: {exp}"
            return False, msg
        
    # Try to connect using ASCOM and retrieving the description

    try:
        SiTech = Dispatch("SiTech.Telescope")
        SiTech.Connected = True
        if (SiTech.Connected):
            msg = f"Connected the {SiTech.Description}"
        else:
            msg = f"{stiExe} connection attempt failed!"
            return False, msg

    except Exception as err:
        msg = f"{stiExe} connection failed - {err}"
        return False, msg
    
    return True, msg


def startMaxIm():
    #
    # start the MaxIm DL app, returing app and camera objects
    #

    try:
        MaxIm = Dispatch("MaxIm.Application")
        time.sleep(5)
        msg = f"MaxIm DL application started"
        print(f"  {msg}")
        logger.info(msg)
        MaxIm.LockApp = True
    except Exception as exp:
        msg = f"Cannot connect MaxIm DL: {exp}"
        logger.exception(msg)
        return False, msg

    try:
        MaxIm.TelescopeConnected = True
        msg = f"Telescope drives connected to MaxIm DL"
        print(f"  {msg}")
        logger.info(msg)
    except Exception as exp:
        msg = f"Cannot connect MaxIm DL to the telescope: {exp}"
        logger.exception(msg)
        return False, msg

    # start the camera

    try:
        MaxCam = Dispatch("MaxIm.CCDCamera")
        time.sleep(5)
        msg = f"MaxIm DL CCDCamera control panel launched"
        print(f"  {msg}")
        logger.info(msg)
    except Exception as exp:
        msg = f"Cannot launch MaxIm DL camera control panel: {exp}"
        print(msg)
        logger.exception(msg)
        print(f"Check physical connection, especially the USB to the guide camera")
        return False, msg
    
    # try to connect the cameras

    try:
        MaxCam.LinkEnabled = True
        msg = f"Cameras linked to MaxIm DL"
        print(f"  {msg}")
        logger.info(msg)
        MaxCam.DisableAutoShutdown = True
    except Exception as exp:
        msg = f"Cannot connect cameras to MaxIM DL: {exp}"
        print(msg)
        logger.exception(msg)
        return False, msg

    # This makes sure MaxIm does not shutdown cameras if all COM objects terminate

    msg = "MaxIm DL startup complete"
    print(f"Done: {msg}")
    logger.info(msg)

    # return objects and msg

    return True, msg


def startFocuser():
    #
    # Start PWI3 Focuser and AutoFocuser systems
    #
    
    logger.info("PWI3 Focuser and AutoFocus system startup")
    print("Connecting Focuser and AutoFocus systems...")

    try:
        Focuser = Dispatch("ASCOM.PWI3.Focuser")
        msg = "Started focuser"
        print(f"  {msg}")
        logger.info(msg)
    except Exception as exp:
        msg = f"Cannot start PWI3 Focuser app: {exp}"
        print(msg)
        logger.exception(msg)
        return False, msg
    
    try:
        AutoFoc = Dispatch("PlaneWave.AutoFocus")
        msg = "Started PlaneWave AutoFocus"
        print(f"  {msg}")
        logger.info(msg)
    except Exception as exp:
        msg = f"Cannot start PWI3 AutoFocus: {exp}"
        print(msg)
        logger.exception(msg)
        return False, msg
        
    # try to connect

    try:
        Focuser.Connected = True
        msg = f"Connected to {Focuser.Description}, Focuser Link Enabled? {YesNo[Focuser.Link]}"
        print(msg)
        logger.info(msg)
    except Exception as exp:
        msg = f"Cannot connect focuser: {exp}"
        print(msg)
        logger.exception(msg)
        return False, msg

    # 5s pause to give apps type to fully initialize
    
    time.sleep(5.0)

    # return objects and message string
    
    return Focuser, AutoFoc, msg


#-----------------------------------
#
# Shutdown all ASCOM links and apps
#

def shutdown(appList):

    logger.info("Starting the DEMONEXT shutdown procedure")

    # Disconnect the ASCOM links

    try:
        if Focuser.Connected:
            msg = f"Disconnecting Hedrick Focuser (PWI3)"
            print(msg)
            logger.info(msg)
            Focuser.Connected = False
            Focuser = None
            AutoFoc = None
    except Exception as exp:
        logger.exception(exp)
        
    try:
        if MaxIm.TelescopeConnected: 
            msg = "Disconnecting the telescope from MaxIm"
            print(msg)
            logger.info(msg)
            MaxIm.TelescopeConnected = False
            time.sleep(2)
            MaxIm.LockApp = False
            MaxIm = None
    except Exception as exp:
        logger.exception(exp)

    try:
        if MaxCam.LinkEnabled:
            msg = "Disconnecting the science and guide cameras from MaxIm"
            print(msg)
            logger.info(msg)
            MaxCam.LinkEnabled = False
            time.sleep(2)
            MaxCam = None
    except Exception as exp:
        logger.exception(exp)

    # Unlock MaxIm DL - allows app to close when all COM object close

    try:
        if SiTech.Connected:
            msg = "Disconnecting the SiTech telescope mount controller (PlaneWave STI)"
            print(msg)
            logger.info(msg)
            SiTech.Connected = False
            time.sleep(2)
            SiTech = None
    except Exception as exp:
        logger.exception(exp)

    # Take down all the apps

    procList = demonext.procList()

    for app in appList:
        if app in procList:
            msg = f"Shutting down {app}..."
            print(msg)
            logger.info(msg)
            try:
                result = os.system(f"taskkill /f /im {exe} /t")
            except Exception as exp: 
                msg = f"Could not shutdown {exe}: {exp}"
                print(msg)
                logger.exception(msg)

    msg = "all apps shutdown"
    logger.info(f"Done: {msg}")
    
    return True, msg

#---------------------------------------------------------------------------
#
# Power Control On/Off
#

def powerDown(outlets=["all"]):
    if outlets[0].lower() == "all":
        logger.info("Powering down all systems")
        msg = "Powered off "
        for outlet in ["ccd","telescope"):
            try:
                pdu.switch(outlet,"off")
                msg = f"{msg} {outlet}=Off"
            except Exception as exp:
                msg = f"Cannot switch off {outlet} - {exp}"
                logger.exception(msg)
        return True, msg
    else:
        for outlet in outlets:
            try:
                pdu.switch(outlet,"off")
            except Exception as exp:
                msg = f"Cannot switch off {outlet} - {exp}"
                logger.exception(msg)
        

#---------------------------------------------------------------------------
#
# main server loop
#

try:
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind((udpAddr,udpPort))
    sock.setblocking(False)
    print(f"UDP server started on {udpAddr}:{udpPort}")
    print("  type \"quit\" or Ctrl+C to exit.")
except Exception as err:
    print(f"Cannot start UDP server - {err}")
    print("dxServer aborting with errors")
    sys.exit(1)

# Server command loop
#  accept commands from the keyboard or UDP socket host.
#  terminate on "quit" from the client or keyboard, or Ctrl+C at keyboard

try:
    while True:
        readData, _, _ = select.select([sys.stdin,sock],[],[],timeout)

        # handle timeout

        if not readData:
            print("Timeout reached, doing housekeeping...")
            continue

        # we got input on the socket or keyboard, process

        for resource in readData:
            if resource is sys.stdin:
                cmdStr = sys.stdin.readline().strip()
                remAddr = None

            elif resource is sock:
                remData, remAddr = sock.recvfrom(1024)
                cmdStr = remData.strip().decode("utf-8")
                if debug: print(f"Got \"{cmdStr}\" from {remAddr}")
                
        # command tree
        
        if len(cmdStr) > 0:
            cmdBits = cmdStr.split()
            cmdWord = cmdBits[0].lower()
            cmdArgs = cmdBits[1:]
            
            if cmdWord == "quit":
                msgStr = "Shutting down the DEMONEXT server"
                cmdReply("done",cmdWord,msgStr,resource,sock,remAddr)
                break

            elif cmdWord == "startup":
                msgStr = "Doing full DEMONEXT system startup..."
                cmdReply("status",cmdWord,msgStr,resource,sock,remAddr)

            elif cmdWord == "shutdown":
                msgStr = "Doing full DEMONEXT system shutdown..."
                cmdReply("status",cmdWord,msgStr,resource,sock,remAddr)

            elif cmdWord == "status":
                msgStr = "DEMONEXT system status is ..."
                cmdReply("status",cmdWord,msgStr,resource,sock,remAddr)

            else:
                msgStr = f"Unrecognized command \"{cmdStr}\""
                cmdReply("error",cmdWord,msgStr,resource,sock,remAddr)

# Ctrl+C handler

except KeyboardInterrupt:
    print("\nReceived Ctrl+C, server aborted at console")
    print("doing shutdown now...")
    sock.close()
    sys.exit(0)
    
finally:
    sock.close()
    sys.exit(0)

print("Got here by quit...")
sock.close()
print("Done, server session shutdown")
sys.exit(0)
