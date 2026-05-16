"""
demonext module - work in progress!

contents as of 2026 Mar 29:
   Config, PDU, Telescope, Camera, Focuser, ObsFile and Site classes 
   general methods obsDate(), homePath(), and procList()
   live testing code as we go with the telescope system in the lab
   additional live testing at Sierra Remote Observatory (Site class)

Modification History:
   2024 Dec 16 - first version, only Config and RaritanPDU classes [rwp/osu]
   2024 Dec 20 - first live test of the Telescope class [rwp/osu]
   2024 Dec 31 - bug fixes and docstring cleanup with spyder [rwp/osu]
   2025 Jan 01 - first live test of the Camera class [rwp/osu]
   2025 Jan 03 - first live test of the Focuser class [rwp/osu]
   2025 Jan 21 - bug fix in procList() [rwp/osu]
   2025 Apr 29 - first live test of the ObsFile class [rwp/osu]
   2026 Mar 29 - first live test of the Site class [rwp/osu]

"""

__all__ = ["config","pdu","telescope","camera","focuser","obsFile","site"]

# import submodules

from . import config
from . import pdu
from . import telescope
from . import camera
from . import focuser
from . import obsfile
from . import site

# modules we require at the top level here

from pathlib import Path

import datetime

# versioning

version = "0.2.1"

# Direct module methods of use

def obsDate():
    """
    Return the observing date string

    Returns
    -------
    string
        observing date in CCYYMMD format, see description.

    Description
    -----------        
    Returns the observing date in CCYYMMDD format.  We define the
    an "observing date" as running from noon to noon local time.
    
    For example, the observing date for the night starting at sunset
    on 2024 Dec 17 and ending at sunrise on 2024 Dec 18 is 20241217

    We use this for filenames for data and logs.
    """

    if float(datetime.datetime.now().strftime("%H")) < 12.0:  # before noon
        return (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    else:
        return datetime.date.today().strftime("%Y%m%d")


def homePath(myPath):
    """
    Convert a relative path to a full qualified path relative to home

    Parameters
    ----------
    myPath : string
        directory path
        
    Returns
    -------
    string
        If myPath is already a full path, returns as-is, otherwise
        a relative path is returned as the full path relative to the
        user's home directory.

    Given myPath, if path has no root return a full qualified
    path relative to the user's home directory.
    
    If myPath already has a root specification, it returns the 
    path string as-is without modification.
    
    This is a convenience function for handling paths which can
    get tricky and prone to typographical errors.
    """

    if len(Path(myPath).root) == 0:  # rootless, assume relative to home
        return str(Path.home() / myPath)
    else:
        return myPath

    
def procList():
    """
    Get a list of all processes running on the Win32 host

    Returns
    -------
    procList : string list
        list of active processes running on the system.

    Description
    -----------
    Uses the win32com.client class to access the Windows Management Instrumentation (WMI) 
    command-line tool `winmgmts` (https://learn.microsoft.com/en-us/windows/win32/wmisdk/winmgmt). 
    This lets us access the process table that would be returned, for example,
    by the windows shell tasklist command, in a machine-readable form we
    can quickly sift through with python.
    """
    from win32com.client import GetObject
    wmi = GetObject("winmgmts:")
    procs = wmi.InstancesOf("win32_process") 
    pList = []
    for proc in procs:
        pList.append(proc.Name)
    return pList
    
