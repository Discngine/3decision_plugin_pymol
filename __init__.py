"""
3decision PyMOL Plugin v1.1

A plugin to search and load structures from 3decision database into PyMOL.

Version: 1.1
"""

import pymol
from pymol import cmd
from pymol.plugins import addmenuitemqt
import sys
import traceback

# Simple logging functions for __init__.py
def log_info(message):
    """Log an info message if logging is enabled"""
    try:
        from .api_client import is_logging_enabled
        if is_logging_enabled():
            print(f"INFO: {message}")
    except:
        # Fallback to always print during initialization
        print(f"INFO: {message}")

def log_error(message):
    """Log an error message if logging is enabled"""
    try:
        from .api_client import is_logging_enabled
        if is_logging_enabled():
            print(f"ERROR: {message}")
    except:
        # Fallback to always print errors during initialization
        print(f"ERROR: {message}")

# Plugin version
__version__ = "1.1"

# Global reference to avoid garbage collection of our dialog
dialog = None

def __init_plugin__(app=None):
    """
    Add the 3decision plugin v1.1 to PyMOL's plugin menu.
    
    This plugin adds itself to:
    1. Plugin menu (standard approach)
    2. Command line access
    """
    try:
        log_info(f"3decision Plugin v{__version__}: Initializing...")
        
        # Add to Plugin menu (this is the standard and supported way)
        addmenuitemqt('3decision', run_3decision_plugin)
        log_info(f"3decision Plugin v{__version__}: Successfully added to Plugin menu")
        
        # Register as a PyMOL command for command-line access
        try:
            from pymol import cmd
            cmd.extend('open_3decision', run_3decision_plugin)
            log_info(f"3decision Plugin v{__version__}: Command 'open_3decision' registered")
            
            # Register utility commands for 3decision metadata
            cmd.extend('get_3decision_id', get_3decision_structure_id)
            cmd.extend('get_3decision_info', get_3decision_info)
            cmd.extend('list_3decision_objects', list_3decision_objects)
            log_info(f"3decision Plugin v{__version__}: Utility commands registered")
        except Exception as cmd_error:
            log_error(f"3decision Plugin v{__version__}: Could not register command: {cmd_error}")
        
    except Exception as e:
        log_error(f"3decision Plugin v{__version__}: Error during initialization: {e}")

def get_3decision_structure_id(object_name):
    """
    Get the 3decision structure ID for a PyMOL object.
    
    Usage: get_3decision_id object_name
    Example: get_3decision_id 1abc
    """
    try:
        from pymol import cmd
        structure_id = cmd.get_property("3decision_structure_id", object_name)
        if structure_id:
            log_info(f"Object '{object_name}' has 3decision structure ID: {structure_id}")
            return structure_id
        else:
            log_info(f"Object '{object_name}' was not loaded from 3decision or has no structure ID")
            return None
    except Exception as e:
        log_error(f"Error getting 3decision structure ID: {e}")
        return None

def get_3decision_info(object_name):
    """
    Get all 3decision metadata for a PyMOL object.
    
    Usage: get_3decision_info object_name
    Example: get_3decision_info 1abc
    """
    try:
        from pymol import cmd
        structure_id = cmd.get_property("3decision_structure_id", object_name)
        external_code = cmd.get_property("3decision_external_code", object_name)
        source = cmd.get_property("3decision_source", object_name)
        
        if structure_id:
            print(f"3decision info for '{object_name}':")
            print(f"  Structure ID: {structure_id}")
            print(f"  External Code: {external_code}")
            print(f"  Source: {source}")
            return {
                "structure_id": structure_id,
                "external_code": external_code,
                "source": source
            }
        else:
            print(f"Object '{object_name}' was not loaded from 3decision")
            return None
    except Exception as e:
        print(f"Error getting 3decision info: {e}")
        return None

def list_3decision_objects():
    """
    List all PyMOL objects that were loaded from 3decision.
    
    Usage: list_3decision_objects
    """
    try:
        from pymol import cmd
        objects = cmd.get_names('objects')
        decision_objects = []
        
        print("Objects loaded from 3decision:")
        for obj in objects:
            structure_id = cmd.get_property("3decision_structure_id", obj)
            if structure_id:
                external_code = cmd.get_property("3decision_external_code", obj)
                decision_objects.append(obj)
                print(f"  {obj} (ID: {structure_id}, Code: {external_code})")
        
        if not decision_objects:
            print("  No objects found that were loaded from 3decision")
            
        return decision_objects
    except Exception as e:
        print(f"Error listing 3decision objects: {e}")
        return []

def run_3decision_plugin():
    """
    Launch the 3decision plugin dialog v1.1.
    """
    global dialog
    
    try:
        log_info(f"3decision Plugin v{__version__}: Starting plugin...")
        log_info(f"3decision Plugin v{__version__}: __file__ = {__file__}")
        log_info(f"3decision Plugin v{__version__}: __name__ = {__name__}")
        
        # Check pymol.Qt availability
        try:
            from pymol.Qt import QtWidgets
            log_info(f"3decision Plugin v{__version__}: pymol.Qt found")
        except ImportError as e:
            log_error(f"3decision Plugin v{__version__}: pymol.Qt import error: {e}")
            return
        
        # Check requests availability
        try:
            import requests
            log_info(f"3decision Plugin v{__version__}: requests library found")
        except ImportError as e:
            log_error(f"3decision Plugin v{__version__}: requests import error: {e}")
            return
        
        # Create or show dialog
        if dialog is None:
            try:
                from .gui import ThreeDecisionDialog
                log_info(f"3decision Plugin v{__version__}: GUI module imported successfully")
            except ImportError as import_error:
                log_error(f"3decision Plugin v{__version__}: GUI import error: {import_error}")
                # Try alternative import methods
                try:
                    import os
                    import sys
                    current_dir = os.path.dirname(__file__)
                    if current_dir not in sys.path:
                        sys.path.insert(0, current_dir)
                    from gui import ThreeDecisionDialog
                    log_info(f"3decision Plugin v{__version__}: GUI module imported via alternative method")
                except Exception as alt_error:
                    log_error(f"3decision Plugin v{__version__}: Alternative import failed: {alt_error}")
                    return
            
            log_info(f"3decision Plugin v{__version__}: Creating dialog...")
            dialog = ThreeDecisionDialog()
        
        log_info(f"3decision Plugin v{__version__}: Showing dialog...")
        dialog.show()
        
    except Exception as e:
        log_error(f"3decision Plugin v{__version__}: Error launching plugin: {e}")
        traceback.print_exc()
        
        # Try to show a simple error dialog
        try:
            from pymol.Qt import QtWidgets
            QtWidgets.QMessageBox.critical(None, "3decision Plugin Error", 
                                         f"Failed to start plugin v{__version__}:\n{str(e)}")
        except:
            pass
