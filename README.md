# DEMONEXT Reboot

Repository of code and hardware/software configuration files for the 2025 DEMONEXT reboot.

This repository was split off from the alpha-level development version on https://github.com/kyleecpi/DEMONEXT after deployment
of the telescope and instrumentation at Sierra Remote Observatories in March 2026, migrating a snapshot of the original alpha
repository on 2026 May 16.  

## Control System Configuration

Files associated with the DEMONEXT control system computer, a Windows10 computer running 
 * MaxIm DL Pro 7 - for integrated telescope mount and instrument control functions (science camera, filter wheel, and guide camera)
 * PlaneWave STI - SiTech mount drive control software from PlaneWave for the Mathis mount
 * PlateWave PWI3 - PlaneWave software for the Hedrick Focuser
 * ASCOM drivers for all devices (SiTech, Finger Lakes camera and filter wheel, ZWO ASI guide camera)

MaxIm DL classes are documented at [MaxIm DL Introduction and Tutorials](https://cdn.diffractionlimited.com/help/maximdl/MaxIm-DL.htm#t=Introduction.htm)

Of specific interest are
 * MaxIm Application class methods and properties
 * MaxIm CCDCamera class methods and properties

The MaxIm help document has a decent search capability, so you can use the cheat-sheet PDF (`MaxIm DL ASCOM Interface.pdf`) to speed navigation 
(for example, search on `CCDCamera.CameraStatus` to find the document for the Camera Status property including the meaning of the integer
status codes returned).

## Working Directories

### Config

Runtime configuration files for the DEMONEXT 2025 system.  

### Scripts

Development versions of python3 scripts to replace the original python2 code.

## Development Jupyter Notebooks

### `DEMONEXT Sandbox.ipynb`

Sandbox that I've used to run functional tests of the system while bringing it up on the new Windows 10
computer with the updated software, and to start development of some of the code we'll need. 

Uses the yaml `demonext.txt` configuration file, in `Config/`

### `ImageAnalysis_GuiderClass.ipynb`

Sandbox for testing the `Guider` class in the `demonext` module in `Scripts/`.  A work in progress as of
2025 Jan 25.  Needs images from the Winer DEMONEXT system, see Rick for how to access the repository on
the ASCTech shared DEMONEXT store.

### `Raritan PDU sandbox.ipynb`

Sandbox for learning how to operate the Raritan PXO power distribution unit (PDU) with the 
Raritan JSON-RPC interface.

Uses the yaml `demonext.txt` configuration file, in `Config`
