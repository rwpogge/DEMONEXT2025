# DEMONEXT control python scripts

**Updated: 2026 Mar 29 [rwp/osu]**

This is where we are developing the python 3 scripts for the DEMONEXT reboot control system.  After
system commissioning, we will transition to a formal release (v1.x).

## Modules and Scripts

### demonext

`demonext` module development, implementing classes we need for robotic operation of the 
DEMONEXT observatory.

#### Current status:

Submodules implemented to date:
 * `config.py` - YAML runtime configuration file handling (`Config` class)
 * `pdu.py` - Raritan power-distribution unit query and control (`RaritanPDU` class)
 * `telescope.py` - telescope mount operation (`Telescope` class) with PlaneWave STI interface and ASCOM
 * `camera.py` - Science and guide camera operation (`Camera` class) with MaxIm DL and ASCOM
 * `focuser.py` - PlaneWave Hedrick focuser operation (`Focuser` class) with PWI3.
 * `obsfile.py` - Observation file handling ('ObsFile` class)
 * `site.py` - Observatory site info for the Sierra Remote Observatory (`Site` class)

### Update Status

On 2024 Dec 20 we installed a 1.8Tb D: data disk drive in the PC where we put all raw imaging data (D:/Data/) and runtime engineering
and data logs (D:/Logs/).

In March 2026, the DEMONEXT telescope was delivered to Sierra Remote Observatories in Auberry, California,
and installed in Building 14 on Pier 6.  At that time we remote-mounted two shared folders on the SRO
site server to access status information the Building 14 roof (open or closed) and weather data from
the SRO weather station. These were incorporated into the `Site` class above (`site.py`).

### Development and testing Jupyter notebooks

 * `DEMONEXT StartUp_Shutdown.ipynb` used to develop and document the startup and shutdown procedures.  We use this to startup and shutdown the system during unit-level code testing.
 * `TelescopeSandbox.ipynb` to develop, test, and document telescope operation (`Telescope` class)
 * `CameraSandbox.ipynb` to develop, test, and document camera (`Camera` class) and focuser (`Focuser` class) operations. Note the filter wheel is controlled through the Camera class.  Tests include telescope interaction.
 * `SRO_Sandbox.ipynb` to develop, test, and document code for reading the SRO site weather data and building roll-off roof status (open or closed).
 * `Site_Sandbox.ipynb` to develop and test the `Site` class

The current versions of all these notebooks were live testing during DEMONEXT installation and post-installation verification and alignment at SRO during the week of 2026 March 15-19.

### Demo programs

 * `dxDemo.py` to debug the runtime config file handling and PDU control (`Config` and `RaritanPDU` classes).  Elements of this are now in the growing suite of sandbox notebooks above.
 * `telDemo.py` for live testing of the Telescope class in the lab - superceded by the `TelescopeSandbox.ipynb` notebook

### ToDo

 * port `guider.py` to a new class to implement SV's original "science guiding" mode from the 2016 system in python 3.
 * incorporate an electronic focuser for the guide telescope for later deployment


### raritanPDU

Demonstration class to implement remote control of the Raritan PXO-2402R-A16 Power Distribution
Unit (PDU) that we use to control and monitor AC power for the PC, telescope drive, and instrument
package on DEMONEXT. 

The PDU we use has 4 switchable but not individually metered AC outlets, one metered input, and a 
DX2-T1H1 peripheral RH/Temp sensor module connected to monitor air temperature and humidity
inside the DEMONEXT electronics box through the PDU.

The code communicates with the PDU using the Raritan Xerxus JSON-RPC API python client bindings.  This
requires the `raritan` python module (https://pypi.org/project/raritan/) installed using `pip install raritan`.

#### Important Note

This version of the Raritan PDU code was for initial test and evaluation to see if the PDU would work for
us. For the DEMONEXT flight code use the `RaritanPDU` class implementation in the `config.py` submodule of the 
`demonext` module.  This class will be moved elsewhere on the GitHub repository after we consolidate and release
the flight code.

