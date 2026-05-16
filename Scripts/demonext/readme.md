# demonext - python module to operate the DEMONEXT robotic telescope

**Update: 0.2.1, 2026 Mar 29**


Python module to operate the DEMONEXT robotic telescope.

## `demonext` - general methods and properties

could use a description here...

### Methods
<dl>
  <dt><code>obsDate()</code> - returns the observing date in CCYYMMDD format.</dt>
  <dd>An "observing date" runs from noon to noon local time with
      a whole night from sunset to sunrise between them. For example, the observing 
      date for the night starting at sunset on 2024 Dec 17 and ending at sunrise on 
      2024 Dec 18 is 20241217</dd>
  <dd>We use a consistent obsDate() for all image and log filenames.</dd>

  <dt><code>homePath(myPath)</code></dt>
  <dd>Given <code>myPath</code>, if not an absolute path relative to some root
  directory, returns full path relative to user home directory</dd>

  <dt><code>procList()</code></dt>
  <dd>Query the Win32 system and return a list of active running processes.  Used
  to see if apps we need are already running.</dd>
</dl>

### Runtime logging

We implement runtime logging using the Python `logging` facility (https://docs.python.org/3/library/logging.html).
The log must started in the main program that uses the `demonext`.  Most of the logging in the `demonext` submodules
is engineering logging of actions, warnings, errors, and exceptions.  We follow the standard semantics of for
logging levels (debug, info, warning, error, critical).

### Runtime configuration

We use YAML-format ASCII text files for all runtime configuration files. This is implemented through the `Config()` class

### Submodules

Submodules of `demonext` define the classes that operate the components of the DEMONEXT robotic observatory.

 * `config.py` - configuration file handling, status: **released**
 * `pdu.py` - power distribution unit (PDU) operation, status: **released**
 * `telescope.py` - telescope operation, status: **released**
 * `camera.py` - science camera operation, status: **beta testing**
 * `focuser.py` - PlaneWave Hedrick focuser operations, status: **beta testing**
 * `guider.py` - science-image guiding code, status: **work in progress**
 * `obsfile.py` - observation file handling, status: **beta testing**
 * `site.py` - observatory site-specific methods, status: **beta testing**

### Dependencies

We use these python modules, * indicates those that must be installed separately
from the standard Anaconda distribution:
 * `raritan`* - Raritan PDU JSON-RPC client bindings for Python
 * `logging` - standard Python logging facility module (https://docs.python.org/3/library/logging.html)
 * `datetime` - for basic date and time handling
 * `yaml` - for runtime configuration files
 * `pathlib` - for file path handling (platform agnostic)
 * `time` - for operation timing and `sleep()` delays
 * `astropy.coordinates` - for coordinate calculations, the `SkyCoord` and `Angle` classes, `TETE` for apparent coords
 * `astropy.units` - units handling for `astropy.coordinates` and others
 * `astropy.time` - for time calcultions, primarily the `Time` class
 * `astropy.io.fits` - for FITS file handling
 * `astroplan` - for observing site circumstances (like Sun altitude), implemented in the `Site` class
 * `pytz` - for robust timezone handling, used in the `Site` class
 * `numpy` - for data arrays
 * `sep`* - python Source Extractor for star finding for science guiding
 * `scipy` - spatial package for kd-tree for object catalog matching for science guiding
 * `win32com.client`* - Windows Common Object Module (COM) package for ASCOM clients and Windows OS-level operations

