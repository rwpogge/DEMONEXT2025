"""DEMONEXT runtime configuration file class

DEMONEXT uses YAML to format its runtime configuration files.  This
class provides simple tools for reading and handling those files in a
consistent way so programs using DEMONEXT configuration files do not
have to reproduce all the YAML file loading and content verification
code.

Author:
   R. Pogge, OSU Astronomy Dept.
   pogge.1@osu.edu
   2024 Dec 14

Modification History:
   2024 Dec 14 - first version [rwp/osu]
   2024 Dec 17 - added logging system (python logging facility) [rwp/osu]
   2024 Dec 29 - docstring cleanup [rwp/osu]
   2024 Dec 31 - bug and docstring cleanup with spyder [rwp/osu]

"""

import os

# we use yaml for configuration file parsing

import yaml

# logging

import logging
logger = logging.getLogger("Config")

# Config Class

class Config:
    """YAML runtime configuration file handling class"""
    
   
    def __init__(self,*args):
        """
        Initialize a Config class instance.

        Parameters
        ----------
        *args : 
            cfgFile : string, optional
                name (including path) of a YAML runtime configuration file

        Raises
        ------
        RuntimeError
            Raised if the configuration file is not found or cannot be opened.

        Returns
        -------
        None.
       
        Description
        -----------
        Initialize a Config class instance and open and load the named
        configuration file.  If no cfgFile is given, it instantiates the
        class but waits until the load() method is invoked to read in the
        runtime configuration file.
    
        """

        if len(args) > 0:
            self.filename = args[0]
        else:
            self.filename = None
 
        # basic initializations of dictionary properties

        self.config = {} # empty dictionary to contain the contents of the configuration file
        self.dicts = [] # empty list of configuration file dictionaries

        # we have a configuration file, open readonly and load using yaml.safe_load()
        
        if self.filename is not None:
            if os.path.exists(self.filename):
                with open(self.filename,"r") as stream:
                    try:
                        self.config = yaml.safe_load(stream)
                    except yaml.YAMLError as exp:
                        msg = f"Cannot open runtime configuration file {self.filename}: {exp}"
                        logger.exception(msg)
                        raise RuntimeError(msg)
            else:
                msg = f"Configuration file {self.filename} not found"
                logger.exception(msg)
                raise RuntimeError(msg)

            # build the list of dictionaries in the config file

            self.dicts = list(self.config.keys())


    # Methods


    def load(self,*args):
        """
        Loads the named YAML-format configuration file.
        
        Parameters
        ----------
        *args : string
            argument is the name of the configuration file to load.

        Raises
        ------
        RuntimeError
            Raised if the config file is not found or cannot be opened.

        Returns
        -------
        dict
            contents of the YAML-format configuration file.
            
        Description
        -----------
        Used if no configuration file was given when the class was 
        instantiated.  If load() is given with no argument it reloads the 
        original configuration file and resets the properties.

        Loading a second configuration files wipes out the first: it does
        not overload the configuration dictionary.        
        """

        if len(args) > 0:
            self.filename = args[0] # new config file, reset properties
            self.config = {} 
            self.dicts = []

        if os.path.exists(self.filename):
            with open(self.filename,"r") as stream:
                try:
                    self.config = yaml.safe_load(stream)
                except yaml.YAMLError as exp:
                    msg = f"Cannot open runtime configuration file {self.filename}: {exp}"
                    logger.exception(msg)
                    raise RuntimeError(msg)
        else:
            msg = f"Configuration file {self.filename} not found"
            logger.exception(msg)
            raise RuntimeError(msg)

        # Build the list of dictionaries in the config file

        self.dicts = list(self.config.keys())
        return self.config


    def print(self):
        """
        Print the contents of the configuration file.
        
        Returns
        -------
        None.
        
        Description
        -----------
        Formatted print to stdout of the contents of the YAML configuration
        file contents in human-readable form.  If no configuration file was
        loaded it says that and does not raise a exception.
        """
        
        if self.filename is None:
            print("No configuration file has been loaded")
        else:
            print(f"\nConfiguration file {self.filename} contents:")
            for key in self.config:
                if isinstance(self.config[key],dict):
                    print(f"\n{key}:")
                    yamlItem = self.config[key]
                    for keyword in yamlItem:
                        print(f"  {keyword}: {yamlItem[keyword]}")
                else:
                    print(f"{key}: {self.config[key]}")


    def printDict(self,name):
        """
        Print the named dictionary block in the configuration file.
        
        Parameters
        ----------
        name : string
            name of dictionary in the YAML.

        Returns
        -------
        None.
        
        Description
        -----------
        Formatted print to stdout of the named dictionary in the YAML 
        configuration file loaded by the constructor or the load() method.

        """

        if name in self.dicts:
            print(f"\n{name}:")
            for key in self.config[name]:
                print(f"  {key}: {self.config[name][key]}")
        else:
            print(f"There is no dictionary '{name}' in {self.filename}")
            
