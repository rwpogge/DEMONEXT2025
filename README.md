# DEMONEXT 2025

Repository of code and hardware/software configuration files for the DEMONEXT reboot project begun in 2025.

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

### demonext

Source folder for the DEMONEXT observatory control system pytho code.

### Config

Runtime configuration files for the DEMONEXT 2025 system.  

### Scripts

Flight python scripts for the SRO DEMONEXT installation

### Documents

Copies of manuals for the DEMONEXT hardwar and associated materials.

### Sandbox

Scripts and notebooks used to develop the 2025 reboot code base, and
for on-going work.

