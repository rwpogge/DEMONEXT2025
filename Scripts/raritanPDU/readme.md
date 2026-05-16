# raritanPDU

Class with methods and properties for communicating with a Raritan PXO power-distribution unit (PDU)
using the Raritan JSON-RPC API python client bindings.

DEMONEXT PDU uses a Raritan PXO-2402R-A16 wtih 4 switchable but not individually metered AC 
outlets and one metered input to control AC power to the main systems: PC, telescope drives,
and science instrument package (FLI CCD, filter wheel, and focuser). 

We have added a Raritan DX2-T1H1 peripheral RH/Temp sensor module that will be deployed inside
the DEMONEXT electronics box to monitor temperature and humidity inside the box through the
PDU.

## Contents:

 * `raritanPDU.py` - Raritan PDU interface class definition
 * `pduStatus.py` - demo program that uses the raritanPDU class to dump status and setup info
 * `outletOnOff.py` - demo program that uses the raritanPDU class to test outlet control
 * `pduInletStats.py` - demo program to collect and compute power usage stats for ~1 minute.
 * `raritanPDU.txt` - YAML-format runtime configuration file with the default setup parameters needed by the `raritanPDU` class.

## Requirements:

 * `raritan` module: Raritan Xerxus JSON-RPC API python bindings from https://pypi.org/project/raritan/
 * `time` module (standard Python)
 * `os` module for the test scripts (standard Python)
 * `pathlib` for platform-agnostic handling of file paths (standard Python)
 * `yaml` for runtime configuration loading (anaconda Python distro)

Install the `raritan` module if not already present in your python using using `pip install raritan` in the Anaconda power shell
so you use the correct python3 environment.

## Documentation:

 * Raritan JSON-RPC API: https://help.raritan.com/json-rpc/4.2.20/

