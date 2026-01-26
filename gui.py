"""
3decision Plugin GUI v1.1

Main dialog and interface components for the 3decision PyMOL plugin.

Version: 1.1
"""

import sys
import json
import time
import requests
from typing import Optional, Dict, List, Any

try:
    # Import from pymol.Qt - the correct way for PyMOL plugins
    from pymol.Qt import QtWidgets, QtCore, QtGui
    from pymol.Qt.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
        QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QHeaderView,
        QProgressBar, QCheckBox, QAbstractItemView, QSplitter, QTabWidget, QWidget
    )
    from pymol.Qt.QtCore import Qt, QThread, pyqtSignal, QTimer
    from pymol.Qt.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor
except ImportError:
    # Fallback for testing outside PyMOL
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
        QTableWidget, QTableWidgetItem, QLabel, QMessageBox, QHeaderView,
        QProgressBar, QCheckBox, QAbstractItemView, QSplitter, QTabWidget, QWidget
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt5.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor

import os

from .api_client import ThreeDecisionAPIClient
from .settings import SettingsDialog


class NumericTableWidgetItem(QTableWidgetItem):
    """Custom QTableWidgetItem that sorts numerically instead of alphabetically"""
    def __init__(self, text, numeric_value):
        super().__init__(text)
        self.numeric_value = numeric_value
    
    def __lt__(self, other):
        """Override less-than comparison for sorting"""
        if isinstance(other, NumericTableWidgetItem):
            return self.numeric_value < other.numeric_value
        return super().__lt__(other)


# Simple logging functions - will check the api_client module for logging state
def log_debug(message):
    """Log a debug message if logging is enabled"""
    # Import here to avoid circular imports
    from .api_client import is_logging_enabled
    if is_logging_enabled():
        print(f"DEBUG: {message}")

def log_error(message):
    """Log an error message if logging is enabled"""
    from .api_client import is_logging_enabled
    if is_logging_enabled():
        print(f"ERROR: {message}")

def log_info(message):
    """Log an info message if logging is enabled"""
    from .api_client import is_logging_enabled
    if is_logging_enabled():
        print(f"INFO: {message}")


class SearchThread(QThread):
    """Thread for handling search operations"""
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self, api_client: ThreeDecisionAPIClient, search_query: str):
        super().__init__()
        self.api_client = api_client
        self.search_query = search_query
        
    def run(self):
        try:
            self.status_update.emit("Submitting search...")
            # Submit search and get job info (now includes structure details)
            job_response = self.api_client.submit_search(self.search_query)
            
            if not job_response:
                self.error_occurred.emit("Failed to submit search")
                return
            
            # Check if we have structure info already included (job completed)
            if 'structures_info' in job_response:
                structures = job_response['structures_info']
                self.status_update.emit(f"Search completed. Found {len(structures)} structures.")
                self.results_ready.emit(structures)
                return
            
            # Check if we need to poll for progress
            if job_response.get('polling_needed'):
                job_id = job_response.get('id')
                queue_name = job_response.get('queue', 'basicSearch')
                
                if not job_id:
                    self.error_occurred.emit("No job ID received from search")
                    return
                
                self.status_update.emit(f"Job submitted (ID: {job_id}). Waiting for completion...")
                
                max_attempts = 60  # 60 attempts with 2-second intervals = 2 minutes max
                attempt = 0
                
                while attempt < max_attempts:
                    try:
                        # Poll the queue endpoint until progress reaches 100
                        result = self.api_client.get_job_status(queue_name, job_id)
                        
                        if result:
                            progress = result.get('progress', 0)
                            self.status_update.emit(f"Search progress: {progress}%")
                            
                            # Check if we have results available (even if progress < 100)
                            structure_ids = []
                            if 'returnvalue' in result and 'STRUCTURE_ID' in result['returnvalue']:
                                structure_ids = result['returnvalue']['STRUCTURE_ID']
                            
                            # Stop polling if job is complete OR if we have empty results
                            if progress == 100 or (isinstance(structure_ids, list) and len(structure_ids) == 0 and progress > 0):
                                if structure_ids:
                                    self.status_update.emit("Fetching structure details...")
                                    structures = self.api_client.get_structures_info(structure_ids)
                                    self.results_ready.emit(structures)
                                else:
                                    self.status_update.emit("Search completed with no results.")
                                    self.results_ready.emit([])
                                return
                            elif result.get('status') == 'failed':
                                self.error_occurred.emit("Search job failed")
                                return
                        
                        # Wait before next poll
                        self.msleep(2000)  # 2 seconds
                        attempt += 1
                        
                    except Exception as e:
                        log_error(f"Polling error: {e}")
                        attempt += 1
                        self.msleep(2000)
                
                self.error_occurred.emit("Search timed out waiting for completion")
                return
                
            # Fallback to old logic for backwards compatibility
            job_id = job_response.get('id')
            queue_name = job_response.get('queue', 'basicSearch')
            
            if not job_id:
                self.error_occurred.emit("No job ID received from search")
                return
                
            # Check if results are already available (direct response)
            if job_response.get('status') == 'completed':
                structure_ids = job_response.get('result', [])
                if structure_ids:
                    self.status_update.emit("Fetching structure details...")
                    structures = self.api_client.get_structures_info(structure_ids)
                    self.results_ready.emit(structures)
                else:
                    self.results_ready.emit([])
                return
                
            self.status_update.emit(f"Polling for results (Job ID: {job_id})...")
            
            # Poll for results (skip if direct response)
            if job_id == 'direct':
                return  # Already handled above
                
            max_attempts = 30  # 30 attempts with 2-second intervals = 1 minute max
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    result = self.api_client.get_job_status(queue_name, job_id)
                    
                    if result and result.get('status') == 'completed':
                        structure_ids = result.get('result', [])
                        if structure_ids:
                            # Get structure details
                            self.status_update.emit("Fetching structure details...")
                            structures = self.api_client.get_structures_info(structure_ids)
                            self.results_ready.emit(structures)
                        else:
                            self.results_ready.emit([])
                        return
                    elif result and result.get('status') == 'failed':
                        self.error_occurred.emit("Search job failed")
                        return
                        
                except Exception as e:
                    log_error(f"Polling attempt {attempt + 1} failed: {e}")
                
                attempt += 1
                self.msleep(2000)  # Wait 2 seconds
                
            self.error_occurred.emit("Search timed out")
            
        except Exception as e:
            self.error_occurred.emit(f"Search error: {str(e)}")


class LoadStructureThread(QThread):
    """Thread for loading structures into PyMOL"""
    structure_loaded = pyqtSignal(str, str)  # structure_id, object_name
    error_occurred = pyqtSignal(str)
    status_update = pyqtSignal(str)
    all_structures_loaded = pyqtSignal()  # Signal when all structures are done loading
    
    def __init__(self, api_client: ThreeDecisionAPIClient, structure_data: List[Dict[str, str]]):
        super().__init__()
        self.api_client = api_client
        self.structure_data = structure_data  # List of {structure_id, external_code}
        
    def run(self):
        try:
            from pymol import cmd
            
            # Check if any structures have transformation matrices
            has_matrices = any(s.get('matrix') is not None for s in self.structure_data)
            
            if has_matrices:
                # Use batch export with transformation matrices
                log_debug("Loading structures with transformation matrices using batch export")
                self.status_update.emit("Loading structures with transformations...")
                
                # Prepare structures for batch export
                structures_with_transforms = []
                for structure_info in self.structure_data:
                    structure_id = int(structure_info['structure_id'])
                    external_code = structure_info['external_code']
                    matrix = structure_info.get('matrix')
                    
                    # Identity matrix as default (no transformation)
                    identity_matrix = [
                        1.0, 0.0, 0.0, 0.0,
                        0.0, 1.0, 0.0, 0.0,
                        0.0, 0.0, 1.0, 0.0,
                        0.0, 0.0, 0.0, 1.0
                    ]
                    
                    if matrix:
                        # Matrix should be a 4x4 nested list, flatten it to 16 values
                        if isinstance(matrix, list) and len(matrix) == 4:
                            flat_matrix = []
                            for row in matrix:
                                if isinstance(row, list) and len(row) == 4:
                                    flat_matrix.extend(row)
                                else:
                                    log_error(f"Invalid matrix row format for structure {structure_id}: {row}")
                                    flat_matrix = None
                                    break
                            
                            if flat_matrix and len(flat_matrix) == 16:
                                structures_with_transforms.append({
                                    "structure_id": structure_id,
                                    "external_code": external_code,
                                    "transform": flat_matrix
                                })
                            else:
                                log_error(f"Invalid matrix format for structure {structure_id}, using identity matrix")
                                structures_with_transforms.append({
                                    "structure_id": structure_id,
                                    "external_code": external_code,
                                    "transform": identity_matrix
                                })
                        else:
                            log_error(f"Invalid matrix structure for {structure_id}, using identity matrix")
                            structures_with_transforms.append({
                                "structure_id": structure_id,
                                "external_code": external_code,
                                "transform": identity_matrix
                            })
                    else:
                        # No matrix provided, use identity matrix (no transformation)
                        log_debug(f"No matrix for structure {structure_id}, using identity matrix")
                        structures_with_transforms.append({
                            "structure_id": structure_id,
                            "external_code": external_code,
                            "transform": identity_matrix
                        })
                
                # Get batch PDB with transformations applied
                pdb_content = self.api_client.export_structures_with_transforms(structures_with_transforms)
                
                if pdb_content:
                    # Load all structures at once from the combined PDB
                    # The PDB will have multiple MODEL entries
                    temp_name = "3decision_batch_temp"
                    cmd.read_pdbstr(pdb_content, temp_name)
                    
                    # Split into individual objects and rename them
                    for structure_info in self.structure_data:
                        structure_id = structure_info['structure_id']
                        external_code = structure_info['external_code']
                        object_name = external_code
                        
                        # Try to extract and rename each model
                        # PyMOL loads multi-model PDB files with state numbers
                        try:
                            # Get the state/model for this structure
                            state_num = self.structure_data.index(structure_info) + 1
                            
                            # Create new object from the state
                            cmd.create(object_name, f"{temp_name}", state_num, 1)
                            
                            # Attach 3decision metadata
                            cmd.set_property("3decision_structure_id", structure_id, object_name)
                            cmd.set_property("3decision_external_code", external_code, object_name)
                            cmd.set_property("3decision_source", "3decision_plugin_v1.1", object_name)
                            
                            log_info(f"3decision Plugin: Loaded {object_name} with structure_id: {structure_id} (with transformation)")
                            self.structure_loaded.emit(structure_id, object_name)
                        except Exception as e:
                            log_error(f"Failed to create object {object_name}: {e}")
                            self.error_occurred.emit(f"Failed to create object {external_code}: {str(e)}")
                    
                    # Delete the temporary combined object
                    try:
                        cmd.delete(temp_name)
                    except:
                        pass
                else:
                    self.error_occurred.emit("Failed to load structures with transformations")
            else:
                # Load structures individually without transformations (search results)
                log_debug("Loading structures individually without transformations")
                for structure_info in self.structure_data:
                    structure_id = structure_info['structure_id']
                    external_code = structure_info['external_code']
                    
                    self.status_update.emit(f"Loading structure {external_code} ({structure_id})...")
                    
                    # Get PDB content
                    pdb_content = self.api_client.export_structure_pdb(structure_id)
                    
                    if pdb_content:
                        # Load into PyMOL using external_code as object name
                        object_name = external_code
                        cmd.read_pdbstr(pdb_content, object_name)
                        
                        # Attach 3decision metadata as object properties
                        cmd.set_property("3decision_structure_id", structure_id, object_name)
                        cmd.set_property("3decision_external_code", external_code, object_name)
                        cmd.set_property("3decision_source", "3decision_plugin_v1.1", object_name)
                        
                        log_info(f"3decision Plugin: Loaded {object_name} with structure_id: {structure_id}")
                        self.structure_loaded.emit(structure_id, object_name)
                    else:
                        self.error_occurred.emit(f"Failed to load structure {external_code} ({structure_id})")
                    
            # Signal that all structures are done loading
            self.all_structures_loaded.emit()
                    
        except Exception as e:
            self.error_occurred.emit(f"Loading error: {str(e)}")


class ThreeDecisionDialog(QDialog):
    """Main 3decision plugin dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = ThreeDecisionAPIClient()
        self.search_thread = None
        self.load_thread = None
        self.all_results = []  # Initialize empty results list for filtering
        self.projects_data = []  # Initialize empty projects list
        self.current_project_structures = []  # Current project structures
        self.projects_loaded = False  # Track if projects have been loaded
        self.init_ui()
        self.check_login_status()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("3decision Structure Search v1.1")
        self.setMinimumSize(800, 600)
        
        # Remove the question mark from the title bar on Windows
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Settings button in top right
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()
        
        self.settings_button = QPushButton()
        self.settings_button.setFixedSize(30, 30)
        self.settings_button.clicked.connect(self.open_settings)
        self.settings_button.setToolTip("Settings")
        
        # Try to load the cog icon
        cog_icon = self.load_cog_icon()
        if cog_icon:
            self.settings_button.setIcon(QIcon(cog_icon))
            self.settings_button.setText("")  # Remove text when icon is available
        else:
            self.settings_button.setText("⚙")  # Fallback to text symbol
            
        settings_layout.addWidget(self.settings_button)
        main_layout.addLayout(settings_layout)
        
        # Tab widget for Search and Projects
        self.tab_widget = QTabWidget()
        
        # Search tab
        self.search_widget = self._create_search_tab()
        self.tab_widget.addTab(self.search_widget, "Search")
        
        # Projects tab
        self.projects_widget = self._create_projects_tab()
        self.tab_widget.addTab(self.projects_widget, "Projects")
        
        main_layout.addWidget(self.tab_widget)
        
        # Status label at bottom
        self.status_label = QLabel("Not logged in")
        self.status_label.setStyleSheet("color: red; padding: 5px;")
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)
    
    def _create_search_tab(self):
        """Create the search tab content"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Search section
        search_layout = QHBoxLayout()
        
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term (e.g., ABL1)")
        self.search_input.returnPressed.connect(self.submit_search)
        search_layout.addWidget(self.search_input)
        
        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self.submit_search)
        self.submit_button.setEnabled(False)
        search_layout.addWidget(self.submit_button)
        
        layout.addLayout(search_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Column filters section
        filters_label = QLabel("Filter Results:")
        filters_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(filters_label)
        
        filters_layout = QHBoxLayout()
        
        # Filter inputs for each column (skip "Select" checkbox column)
        self.filter_external_code = QLineEdit()
        self.filter_external_code.setPlaceholderText("External Code")
        self.filter_external_code.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.filter_external_code)
        
        self.filter_label = QLineEdit()
        self.filter_label.setPlaceholderText("Label")
        self.filter_label.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.filter_label)
        
        self.filter_title = QLineEdit()
        self.filter_title.setPlaceholderText("Title")
        self.filter_title.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.filter_title)
        
        self.filter_method = QLineEdit()
        self.filter_method.setPlaceholderText("Method")
        self.filter_method.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.filter_method)
        
        # Resolution filter with range support (min-max)
        self.filter_resolution = QLineEdit()
        self.filter_resolution.setPlaceholderText("Resolution (e.g., <2.0 or 1.5-3.0)")
        self.filter_resolution.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.filter_resolution)
        
        self.filter_source = QLineEdit()
        self.filter_source.setPlaceholderText("Source")
        self.filter_source.textChanged.connect(self.apply_filters)
        filters_layout.addWidget(self.filter_source)
        
        # Clear filters button
        clear_filters_btn = QPushButton("Clear Filters")
        clear_filters_btn.clicked.connect(self.clear_filters)
        filters_layout.addWidget(clear_filters_btn)
        
        layout.addLayout(filters_layout)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "External Code", "Label", "Title", "Method", "Resolution", "Source"
        ])
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Disable editing
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.setAlternatingRowColors(True)
        
        # Enable sorting by clicking column headers
        self.results_table.setSortingEnabled(True)
        
        layout.addWidget(self.results_table)
        
        # Load button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.load_button = QPushButton("Load Selected in PyMOL")
        self.load_button.clicked.connect(self.load_selected_structures)
        self.load_button.setEnabled(False)
        button_layout.addWidget(self.load_button)
        
        layout.addLayout(button_layout)
        
        widget.setLayout(layout)
        return widget
    
    def _create_projects_tab(self):
        """Create the projects tab content"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Instructions
        layout.addWidget(QLabel("Browse and load structures from your 3decision projects"))
        
        # Projects table
        layout.addWidget(QLabel("Projects:"))
        
        # Projects filters (above table)
        projects_filters_layout = QHBoxLayout()
        
        self.projects_filter_name = QLineEdit()
        self.projects_filter_name.setPlaceholderText("Project Name")
        self.projects_filter_name.textChanged.connect(self.apply_projects_filters)
        projects_filters_layout.addWidget(self.projects_filter_name)
        
        self.projects_filter_owner = QLineEdit()
        self.projects_filter_owner.setPlaceholderText("Owner")
        self.projects_filter_owner.textChanged.connect(self.apply_projects_filters)
        projects_filters_layout.addWidget(self.projects_filter_owner)
        
        self.projects_filter_structures = QLineEdit()
        self.projects_filter_structures.setPlaceholderText("Structures (e.g., >10)")
        self.projects_filter_structures.textChanged.connect(self.apply_projects_filters)
        projects_filters_layout.addWidget(self.projects_filter_structures)
        
        self.projects_filter_id = QLineEdit()
        self.projects_filter_id.setPlaceholderText("Project ID")
        self.projects_filter_id.textChanged.connect(self.apply_projects_filters)
        projects_filters_layout.addWidget(self.projects_filter_id)
        
        # Clear projects filters button
        clear_projects_filters_btn = QPushButton("Clear Filters")
        clear_projects_filters_btn.clicked.connect(self.clear_projects_filters)
        projects_filters_layout.addWidget(clear_projects_filters_btn)
        
        layout.addLayout(projects_filters_layout)
        
        self.projects_table = QTableWidget()
        self.projects_table.setColumnCount(4)
        self.projects_table.setHorizontalHeaderLabels([
            "Project Name", "Owner", "Structures", "Project ID"
        ])
        
        # Configure table
        header = self.projects_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.resizeSection(0, 200)  # Project Name
        header.resizeSection(1, 120)  # Owner
        header.resizeSection(2, 80)   # Structures
        header.resizeSection(3, 150)  # Project ID
        
        self.projects_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.projects_table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Disable editing
        self.projects_table.setAlternatingRowColors(True)
        self.projects_table.setSortingEnabled(True)
        self.projects_table.itemSelectionChanged.connect(self.on_project_selection_changed)
        
        layout.addWidget(self.projects_table)
        
        # Projects buttons
        projects_buttons = QHBoxLayout()
        refresh_button = QPushButton("Refresh Projects")
        refresh_button.clicked.connect(self.load_projects_for_tab)
        projects_buttons.addWidget(refresh_button)
        projects_buttons.addStretch()
        layout.addLayout(projects_buttons)
        
        # Project structures list below
        layout.addWidget(QLabel("Project Structures (click to select):"))
        
        # Column filters for project structures
        project_filters_layout = QHBoxLayout()
        
        self.project_filter_external_code = QLineEdit()
        self.project_filter_external_code.setPlaceholderText("External Code")
        self.project_filter_external_code.textChanged.connect(self.apply_project_filters)
        project_filters_layout.addWidget(self.project_filter_external_code)
        
        self.project_filter_label = QLineEdit()
        self.project_filter_label.setPlaceholderText("Label")
        self.project_filter_label.textChanged.connect(self.apply_project_filters)
        project_filters_layout.addWidget(self.project_filter_label)
        
        self.project_filter_title = QLineEdit()
        self.project_filter_title.setPlaceholderText("Title")
        self.project_filter_title.textChanged.connect(self.apply_project_filters)
        project_filters_layout.addWidget(self.project_filter_title)
        
        self.project_filter_method = QLineEdit()
        self.project_filter_method.setPlaceholderText("Method")
        self.project_filter_method.textChanged.connect(self.apply_project_filters)
        project_filters_layout.addWidget(self.project_filter_method)
        
        # Clear filters button
        clear_project_filters_btn = QPushButton("Clear Filters")
        clear_project_filters_btn.clicked.connect(self.clear_project_filters)
        project_filters_layout.addWidget(clear_project_filters_btn)
        
        layout.addLayout(project_filters_layout)
        
        self.project_structures_table = QTableWidget()
        self.project_structures_table.setColumnCount(4)
        self.project_structures_table.setHorizontalHeaderLabels([
            "External Code", "Label", "Title", "Method"
        ])
        self.project_structures_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.project_structures_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.project_structures_table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Disable editing
        self.project_structures_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.project_structures_table.setAlternatingRowColors(True)
        self.project_structures_table.setSortingEnabled(True)
        
        layout.addWidget(self.project_structures_table)
        
        # Structure selection buttons
        structure_buttons = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_project_structures)
        structure_buttons.addWidget(select_all_btn)
        
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self.select_none_project_structures)
        structure_buttons.addWidget(select_none_btn)
        
        structure_buttons.addStretch()
        
        self.load_project_structures_button = QPushButton("Load Selected Structures")
        self.load_project_structures_button.clicked.connect(self.load_selected_project_structures)
        self.load_project_structures_button.setEnabled(False)
        structure_buttons.addWidget(self.load_project_structures_button)
        
        layout.addLayout(structure_buttons)
        
        widget.setLayout(layout)
        return widget
    
    def load_projects_for_tab(self):
        """Load projects when Projects tab is accessed"""
        try:
            # Check authentication first
            if not self.api_client.is_authenticated():
                log_debug("Not authenticated, attempting to authenticate with saved token")
                # Try to authenticate with saved token
                if self.api_client.test_connection():
                    log_debug("Successfully authenticated with saved token")
                    self.check_login_status()
                else:
                    # Authentication failed, prompt user
                    reply = QMessageBox.question(
                        self,
                        "Authentication Required",
                        "You need to be logged in to view projects.\n\n"
                        "Would you like to open settings to configure your API token?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    
                    if reply == QMessageBox.Yes:
                        self.open_settings()
                    return
            
            projects = self.api_client.get_projects()
            
            # Filter out the "3decision" project
            filtered_projects = []
            for project in projects:
                project_label = project.get('project_label', '').lower()
                project_name = project.get('project_name', '').lower()
                
                # Skip if project label or name is "3decision"
                if project_label != '3decision' and project_name != '3decision':
                    filtered_projects.append(project)
                else:
                    log_debug(f"Filtering out 3decision system project: {project.get('project_label', '')}")
            
            self.projects_data = filtered_projects
            self.populate_projects_table()
        except Exception as e:
            log_error(f"Failed to load projects: {e}")
            
            # Check if it's an authentication error
            error_str = str(e).lower()
            if 'auth' in error_str or 'token' in error_str or '401' in error_str or '403' in error_str:
                reply = QMessageBox.critical(
                    self,
                    "Authentication Error",
                    f"Failed to load projects: {str(e)}\n\n"
                    "Your authentication token may have expired.\n"
                    "Would you like to open settings to update your API token?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    self.open_settings()
            else:
                QMessageBox.critical(self, "Error", f"Failed to load projects: {str(e)}")
    
    def populate_projects_table(self):
        """Populate the projects table with data"""
        # Disable sorting while populating for better performance
        self.projects_table.setSortingEnabled(False)
        
        self.projects_table.setRowCount(len(self.projects_data))
        
        # Debug: Log the structure of the first project to help identify owner field
        if self.projects_data:
            log_debug(f"Project data structure (first project): {json.dumps(self.projects_data[0], indent=2)}")
        
        for row, project in enumerate(self.projects_data):
            # Project Name
            name_item = QTableWidgetItem(project.get('project_label', ''))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            # Store the full project data in the first column for easy retrieval
            name_item.setData(Qt.UserRole, project)
            self.projects_table.setItem(row, 0, name_item)
            
            # Owner - try multiple possible field names for project owner
            owner_field = None
            owner = None
            for field in ['owner', 'project_owner', 'created_by', 'owner_username', 'creator', 'author', 'username']:
                if project.get(field):
                    owner = project.get(field)
                    owner_field = field
                    break
            
            if not owner:
                owner = ''
                owner_field = 'none'
            
            # Debug: Log which field was used for owner (only for first project to avoid spam)
            if row == 0:
                log_debug(f"Using '{owner_field}' field for project owner: '{owner}'")
                
            owner_item = QTableWidgetItem(str(owner))
            owner_item.setFlags(owner_item.flags() & ~Qt.ItemIsEditable)
            self.projects_table.setItem(row, 1, owner_item)
            
            # Structures count - use numeric sorting
            count = project.get('count_structures_in_project', 0)
            count_item = NumericTableWidgetItem(str(count), count)
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.projects_table.setItem(row, 2, count_item)
            
            # Project ID
            id_item = QTableWidgetItem(str(project.get('project_id', '')))
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.projects_table.setItem(row, 3, id_item)
        
        # Re-enable sorting after populating
        self.projects_table.setSortingEnabled(True)
    
    def on_project_selection_changed(self):
        """Handle project table selection change"""
        selected_rows = self.projects_table.selectionModel().selectedRows()
        if selected_rows:
            self.load_project_structures_button.setEnabled(False)
            # Load structures for selected project
            row = selected_rows[0].row()
            project_data = self.projects_table.item(row, 0).data(Qt.UserRole)
            project_id = project_data.get('project_id')
            self.load_project_structures_in_tab(project_id)
    
    def load_project_structures_in_tab(self, project_id):
        """Load structures for the selected project"""
        try:
            # Get basic project structures (with transformation matrices)
            structures = self.api_client.get_project_structures(project_id)
            
            log_debug(f"Received {len(structures)} structures from get_project_structures")
            if structures:
                # Log first structure to see its format
                log_debug(f"First structure from API: {json.dumps(structures[0], indent=2)}")
            
            if not structures:
                self.current_project_structures = []
                self.populate_project_structures_table([])
                return
            
            # Extract structure IDs to fetch full details
            structure_ids = []
            for s in structures:
                structure_id = s.get('STRUCTURE_ID') or s.get('structure_id')
                if structure_id:
                    structure_ids.append(int(structure_id))
            
            log_debug(f"Fetching details for {len(structure_ids)} structures...")
            
            # Fetch full structure details
            detailed_structures = self.api_client.get_structures_info(structure_ids)
            
            # Create a map of structure_id -> full details
            details_map = {}
            for detail in detailed_structures:
                sid = detail.get('structure_id') or detail.get('general', {}).get('structure_id')
                if sid:
                    details_map[int(sid)] = detail
            
            # Merge the transformation matrix data with full details
            enriched_structures = []
            for s in structures:
                structure_id = s.get('STRUCTURE_ID') or s.get('structure_id')
                if structure_id and int(structure_id) in details_map:
                    # Start with the full details
                    enriched = details_map[int(structure_id)].copy()
                    # Add the transformation matrix from project structures
                    # Matrix is in ReferenceTransforms.transform (flat 16-value array)
                    matrix = None
                    ref_transforms = s.get('ReferenceTransforms')
                    if ref_transforms and isinstance(ref_transforms, dict):
                        transform = ref_transforms.get('transform')
                        if transform and isinstance(transform, list) and len(transform) == 16:
                            # Convert flat 16-value array to 4x4 nested array
                            matrix = [
                                transform[0:4],
                                transform[4:8],
                                transform[8:12],
                                transform[12:16]
                            ]
                    enriched['TRANSFORM_MATRIX'] = matrix
                    log_debug(f"Structure {structure_id}: has matrix = {matrix is not None}")
                    enriched_structures.append(enriched)
                else:
                    # Fallback to basic data if details not found
                    enriched_structures.append(s)
            
            self.current_project_structures = enriched_structures
            self.populate_project_structures_table(enriched_structures)
            
        except Exception as e:
            log_error(f"Failed to load project structures: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load project structures: {str(e)}")
    
    def populate_project_structures_table(self, structures):
        """Populate the project structures table"""
        self.project_structures_table.setSortingEnabled(False)
        self.project_structures_table.setRowCount(len(structures))
        
        # Debug: Log the structure of the first structure to understand the data format
        if structures:
            log_debug(f"Project structure data format (first structure): {json.dumps(structures[0], indent=2)}")
        
        for row, structure in enumerate(structures):
            # Project structures use UPPERCASE field names at top level
            # Try uppercase first, then lowercase, then check 'general' field as fallback
            external_code = (structure.get('EXTERNAL_CODE') or 
                           structure.get('external_code') or 
                           structure.get('general', {}).get('external_code', 'N/A'))
            
            item = QTableWidgetItem(external_code)
            
            # Store structure_id and transformation matrix - try all possible field name variations
            structure_id = (structure.get('STRUCTURE_ID') or 
                          structure.get('structure_id') or 
                          structure.get('general', {}).get('structure_id'))
            
            # Get transformation matrix (could be TRANSFORM_MATRIX, matrix, or MATRIX)
            transform_matrix = (structure.get('TRANSFORM_MATRIX') or 
                              structure.get('matrix') or 
                              structure.get('MATRIX'))
            
            # Store both structure_id and matrix as a dict in UserRole
            item.setData(Qt.UserRole, {
                'structure_id': structure_id,
                'matrix': transform_matrix
            })
            self.project_structures_table.setItem(row, 0, item)
            
            # Label - project structures might not have this field
            label = (structure.get('LABEL') or 
                    structure.get('label') or 
                    structure.get('PROJECT_LABEL') or 
                    structure.get('project_label') or
                    structure.get('general', {}).get('label', external_code))
            self.project_structures_table.setItem(row, 1, QTableWidgetItem(label))
            
            # Title - project structures might not have this field, use external_code as fallback
            title = (structure.get('TITLE') or 
                    structure.get('title') or 
                    structure.get('general', {}).get('title', external_code))
            self.project_structures_table.setItem(row, 2, QTableWidgetItem(title))
            
            # Method - project structures might not have this field
            method = (structure.get('METHOD') or 
                     structure.get('method') or 
                     structure.get('general', {}).get('method', 'N/A'))
            self.project_structures_table.setItem(row, 3, QTableWidgetItem(method))
        
        self.project_structures_table.setSortingEnabled(True)
        self.load_project_structures_button.setEnabled(len(structures) > 0)
    
    def select_all_project_structures(self):
        """Select all structures in the project structures table"""
        self.project_structures_table.selectAll()
    
    def select_none_project_structures(self):
        """Deselect all structures in the project structures table"""
        self.project_structures_table.clearSelection()
    
    def load_selected_project_structures(self):
        """Load selected structures from the project"""
        selected_structures = []
        
        selected_rows = self.project_structures_table.selectionModel().selectedRows()
        log_debug(f"Found {len(selected_rows)} selected rows")
        
        for index in selected_rows:
            row = index.row()
            item = self.project_structures_table.item(row, 0)
            if item:
                data = item.data(Qt.UserRole)
                external_code = item.text()
                
                # Data is now a dict with structure_id and matrix
                if isinstance(data, dict):
                    structure_id = data.get('structure_id')
                    matrix = data.get('matrix')
                    log_debug(f"Row {row}: structure_id={structure_id}, external_code={external_code}, has_matrix={matrix is not None}")
                else:
                    # Fallback for old format (just structure_id)
                    structure_id = data
                    matrix = None
                    log_debug(f"Row {row}: structure_id={structure_id}, external_code={external_code} (no matrix)")
                
                if structure_id:
                    selected_structures.append({
                        'structure_id': str(structure_id),
                        'external_code': external_code,
                        'matrix': matrix  # Include transformation matrix
                    })
                else:
                    log_error(f"Row {row}: structure_id is None!")
        
        log_debug(f"Total selected structures: {len(selected_structures)}")
        
        if not selected_structures:
            QMessageBox.warning(self, "Warning", "Please select at least one structure to load")
            return
        
        # Start loading in background thread (reuse the same loading logic)
        self.load_thread = LoadStructureThread(self.api_client, selected_structures)
        self.load_thread.structure_loaded.connect(self.handle_structure_loaded)
        self.load_thread.error_occurred.connect(self.handle_load_error)
        self.load_thread.status_update.connect(self.update_project_status)
        self.load_thread.all_structures_loaded.connect(self.handle_all_structures_loaded)
        
        self.load_project_structures_button.setEnabled(False)
        self.status_label.setText("Loading structures...")
        
        self.load_thread.start()
    
    def update_project_status(self, message: str):
        """Update status message for project loading"""
        self.status_label.setText(message)
        
    def is_dark_theme(self):
        """Detect if the current environment uses a dark theme"""
        try:
            # Get the window's background color
            palette = self.palette()
            bg_color = palette.color(palette.Window)
            
            # Calculate luminance using the standard formula
            # If luminance is low, it's a dark theme
            luminance = (0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()) / 255.0
            
            # Return True if dark (luminance < 0.5)
            is_dark = luminance < 0.5
            log_debug(f"Theme detection: background RGB({bg_color.red()}, {bg_color.green()}, {bg_color.blue()}), luminance: {luminance:.3f}, dark: {is_dark}")
            return is_dark
            
        except Exception as e:
            log_debug(f"Theme detection error: {e}, defaulting to light theme")
            return False
        
    def load_logo(self):
        """Load the logo image from the images folder based on theme"""
        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Determine which logo to use based on theme
        if self.is_dark_theme():
            logo_filename = "3decision_RVB_White_transparent.png"  # White logo for dark background
            fallback_filename = "3decision_RVB_Dark_transparent.png"  # Fallback dark logo
        else:
            logo_filename = "3decision_RVB_Dark_transparent.png"  # Dark logo for light background  
            fallback_filename = "3decision_RVB_White_transparent.png"  # Fallback white logo
        
        # Look for preferred logo in possible locations
        possible_paths = [
            os.path.join(current_dir, "images", logo_filename),
            os.path.join(current_dir, "..", "images", logo_filename),
            os.path.join(os.path.dirname(current_dir), "images", logo_filename),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    log_debug(f"Loaded logo: {logo_filename}")
                    return pixmap
        
        # Try fallback logo if preferred not found
        fallback_paths = [
            os.path.join(current_dir, "images", fallback_filename),
            os.path.join(current_dir, "..", "images", fallback_filename),
            os.path.join(os.path.dirname(current_dir), "images", fallback_filename),
        ]
        
        for path in fallback_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    log_debug(f"Loaded fallback logo: {fallback_filename}")
                    return pixmap
        
        # Final fallback to LogoTitle2.0.png if available
        final_fallback_paths = [
            os.path.join(current_dir, "images", "LogoTitle2.0.png"),
            os.path.join(current_dir, "..", "images", "LogoTitle2.0.png"),
            os.path.join(os.path.dirname(current_dir), "images", "LogoTitle2.0.png"),
        ]
        
        for path in final_fallback_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    log_debug(f"Loaded final fallback logo: LogoTitle2.0.png")
                    return pixmap
                    
        log_debug("No logo found")
        return None
        
    def load_cog_icon(self):
        """Load the cog icon image from the images folder based on theme"""
        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Determine which cog icon to use based on theme
        if self.is_dark_theme():
            cog_filename = "cog-16-white.png"
            fallback_filename = "cog-16-dark.png"  # Fallback if white cog not found
        else:
            cog_filename = "cog-16-dark.png"  # Use dark icon for light theme
            fallback_filename = "cog-16-white.png"  # Fallback if dark cog not found
        
        # Look for preferred cog icon in possible locations
        possible_paths = [
            os.path.join(current_dir, "images", cog_filename),
            os.path.join(current_dir, "..", "images", cog_filename),
            os.path.join(os.path.dirname(current_dir), "images", cog_filename),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    log_debug(f"Loaded cog icon: {cog_filename}")
                    return pixmap
        
        # Try fallback cog icon if preferred not found
        fallback_paths = [
            os.path.join(current_dir, "images", fallback_filename),
            os.path.join(current_dir, "..", "images", fallback_filename),
            os.path.join(os.path.dirname(current_dir), "images", fallback_filename),
        ]
        
        for path in fallback_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    log_debug(f"Loaded fallback cog icon: {fallback_filename}")
                    return pixmap
                    
        log_debug("No cog icon found")
        return None
        
    def load_arrow(self):
        """Load the arrow image from the images folder"""
        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Look for arrow image in possible locations
        possible_paths = [
            os.path.join(current_dir, "images", "arrows.png"),
            os.path.join(current_dir, "..", "images", "arrows.png"),
            os.path.join(os.path.dirname(current_dir), "images", "arrows.png"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    return pixmap
                    
        return None
        
    def load_pymol_logo(self):
        """Load the PyMOL logo image from the images folder"""
        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Look for PyMOL logo in possible locations
        possible_paths = [
            os.path.join(current_dir, "images", "PyMOL_logo.png"),
            os.path.join(current_dir, "..", "images", "PyMOL_logo.png"),
            os.path.join(os.path.dirname(current_dir), "images", "PyMOL_logo.png"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    return pixmap
                    
        return None
        
    def check_login_status(self):
        """Check if user is logged in and update UI accordingly"""
        if self.api_client.is_configured() and self.api_client.test_connection():
            self.status_label.setText("✓ Logged in successfully")
            self.status_label.setStyleSheet("color: #28ca42;")  # macOS green color
            self.submit_button.setEnabled(True)
            
            # Load projects when logged in (if not already loaded)
            if hasattr(self, 'projects_table') and not hasattr(self, 'projects_loaded'):
                self.projects_loaded = False
                try:
                    self.load_projects_for_tab()
                    self.projects_loaded = True
                except Exception as e:
                    log_error(f"Failed to auto-load projects: {e}")
        else:
            self.status_label.setText("✗ Not logged in - click ⚙ to configure")
            self.status_label.setStyleSheet("color: red;")
            self.submit_button.setEnabled(False)
            
    def open_settings(self):
        """Open the settings dialog"""
        dialog = SettingsDialog(self.api_client, self)
        if dialog.exec_() == QDialog.Accepted:
            self.check_login_status()
            
    def submit_search(self):
        """Submit search query"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Warning", "Please enter a search term")
            return
            
        if not self.api_client.is_configured():
            QMessageBox.warning(self, "Warning", "Please configure API settings first")
            return
            
        # Start search in background thread
        self.search_thread = SearchThread(self.api_client, query)
        self.search_thread.results_ready.connect(self.display_results)
        self.search_thread.error_occurred.connect(self.handle_search_error)
        self.search_thread.status_update.connect(self.update_status)
        
        self.submit_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        self.search_thread.start()
        
    def update_status(self, message: str):
        """Update status message"""
        self.status_label.setText(message)
        
    def display_results(self, structures: List[Dict[str, Any]]):
        """Display search results in the table"""
        self.progress_bar.setVisible(False)
        self.submit_button.setEnabled(True)
        self.check_login_status()  # Restore login status
        
        # Store all results for filtering
        self.all_results = structures
        
        # Display all results initially (without triggering filters)
        self.populate_results_table(structures)
        
        # Show result count message
        if len(structures) == 0:
            QMessageBox.information(self, "Search Results", "No structures found for your search query.")
        else:
            QMessageBox.information(self, "Search Results", f"Found {len(structures)} structures.")
        
    def populate_results_table(self, structures: List[Dict[str, Any]]):
        """Populate the results table with given structures"""
        # Disable sorting while populating the table for better performance
        self.results_table.setSortingEnabled(False)
        
        self.results_table.setRowCount(len(structures))
        
        for row, structure in enumerate(structures):
            general = structure.get('general', {})
            
            # External code
            external_code = general.get('external_code', 'N/A')
            item = QTableWidgetItem(external_code)
            # Store structure_id in user data
            item.setData(Qt.UserRole, general.get('structure_id'))
            self.results_table.setItem(row, 0, item)
            
            # Label
            label = general.get('label', 'N/A')
            self.results_table.setItem(row, 1, QTableWidgetItem(label))
            
            # Title
            title = general.get('title', 'N/A')
            self.results_table.setItem(row, 2, QTableWidgetItem(title))
            
            # Method
            method = general.get('method', 'N/A')
            self.results_table.setItem(row, 3, QTableWidgetItem(method))
            
            # Resolution - use custom numeric sorting
            resolution = general.get('resolution')
            resolution_text = f"{resolution:.2f} Å" if resolution else "N/A"
            # Use large number for N/A to sort to the end
            numeric_value = resolution if resolution is not None else float('inf')
            resolution_item = NumericTableWidgetItem(resolution_text, numeric_value)
            self.results_table.setItem(row, 4, resolution_item)
            
            # Source
            source = general.get('source', 'N/A')
            self.results_table.setItem(row, 5, QTableWidgetItem(source))
        
        # Re-enable sorting after populating
        self.results_table.setSortingEnabled(True)
        
        self.load_button.setEnabled(len(structures) > 0)
            
    def handle_search_error(self, error_message: str):
        """Handle search errors"""
        self.progress_bar.setVisible(False)
        self.submit_button.setEnabled(True)
        self.check_login_status()  # Restore login status
        QMessageBox.critical(self, "Search Error", error_message)
    
    def clear_filters(self):
        """Clear all filter inputs without triggering filtering"""
        # Block signals to prevent triggering apply_filters while clearing
        self.filter_external_code.blockSignals(True)
        self.filter_label.blockSignals(True)
        self.filter_title.blockSignals(True)
        self.filter_method.blockSignals(True)
        self.filter_resolution.blockSignals(True)
        self.filter_source.blockSignals(True)
        
        self.filter_external_code.clear()
        self.filter_label.clear()
        self.filter_title.clear()
        self.filter_method.clear()
        self.filter_resolution.clear()
        self.filter_source.clear()
        
        # Unblock signals
        self.filter_external_code.blockSignals(False)
        self.filter_label.blockSignals(False)
        self.filter_title.blockSignals(False)
        self.filter_method.blockSignals(False)
        self.filter_resolution.blockSignals(False)
        self.filter_source.blockSignals(False)
        
        # Reset status label if we have results
        if hasattr(self, 'all_results') and self.all_results:
            self.status_label.setText(f"Showing all {len(self.all_results)} results")
    
    def apply_filters(self):
        """Apply column filters to the results table"""
        if not hasattr(self, 'all_results') or not self.all_results:
            return
        
        # Get filter values
        filter_ext_code = self.filter_external_code.text().strip().lower()
        filter_lbl = self.filter_label.text().strip().lower()
        filter_ttl = self.filter_title.text().strip().lower()
        filter_mth = self.filter_method.text().strip().lower()
        filter_res = self.filter_resolution.text().strip()
        filter_src = self.filter_source.text().strip().lower()
        
        # Parse resolution filter
        res_min, res_max, res_operator = self.parse_resolution_filter(filter_res)
        
        # Filter structures
        filtered_structures = []
        for structure in self.all_results:
            general = structure.get('general', {})
            
            # Text filters (case-insensitive contains)
            if filter_ext_code and filter_ext_code not in general.get('external_code', '').lower():
                continue
            if filter_lbl and filter_lbl not in general.get('label', '').lower():
                continue
            if filter_ttl and filter_ttl not in general.get('title', '').lower():
                continue
            if filter_mth and filter_mth not in general.get('method', '').lower():
                continue
            if filter_src and filter_src not in general.get('source', '').lower():
                continue
            
            # Resolution filter (numeric)
            if filter_res:
                resolution = general.get('resolution')
                if not self.check_resolution_filter(resolution, res_min, res_max, res_operator):
                    continue
            
            filtered_structures.append(structure)
        
        # Update table with filtered results
        self.populate_results_table(filtered_structures)
        
        # Update status
        if len(filtered_structures) < len(self.all_results):
            self.status_label.setText(f"Showing {len(filtered_structures)} of {len(self.all_results)} results")
        else:
            self.status_label.setText(f"Showing all {len(self.all_results)} results")
    
    def parse_resolution_filter(self, filter_text: str):
        """
        Parse resolution filter string.
        Supports formats: <2.0, >1.5, <=2.0, >=1.5, 1.5-3.0, 2.0
        Returns: (min_value, max_value, operator)
        """
        if not filter_text:
            return None, None, None
        
        filter_text = filter_text.strip()
        
        # Range format: 1.5-3.0
        if '-' in filter_text and not filter_text.startswith('-'):
            parts = filter_text.split('-')
            if len(parts) == 2:
                try:
                    min_val = float(parts[0].strip())
                    max_val = float(parts[1].strip())
                    return min_val, max_val, 'range'
                except ValueError:
                    return None, None, None
        
        # Operator formats: <, >, <=, >=
        if filter_text.startswith('<='):
            try:
                val = float(filter_text[2:].strip())
                return None, val, '<='
            except ValueError:
                return None, None, None
        elif filter_text.startswith('>='):
            try:
                val = float(filter_text[2:].strip())
                return val, None, '>='
            except ValueError:
                return None, None, None
        elif filter_text.startswith('<'):
            try:
                val = float(filter_text[1:].strip())
                return None, val, '<'
            except ValueError:
                return None, None, None
        elif filter_text.startswith('>'):
            try:
                val = float(filter_text[1:].strip())
                return val, None, '>'
            except ValueError:
                return None, None, None
        
        # Exact value or equals
        try:
            val = float(filter_text)
            return val, val, '='
        except ValueError:
            return None, None, None
    
    def check_resolution_filter(self, resolution, min_val, max_val, operator):
        """Check if resolution value passes the filter"""
        if resolution is None:
            return False  # N/A values don't pass numeric filters
        
        if operator == 'range':
            return min_val <= resolution <= max_val
        elif operator == '<':
            return resolution < max_val
        elif operator == '<=':
            return resolution <= max_val
        elif operator == '>':
            return resolution > min_val
        elif operator == '>=':
            return resolution >= min_val
        elif operator == '=':
            # Allow small tolerance for floating point comparison
            return abs(resolution - min_val) < 0.01
        
        return True
    
    def clear_projects_filters(self):
        """Clear all projects filter inputs without triggering filtering"""
        # Block signals to prevent triggering apply_projects_filters while clearing
        self.projects_filter_name.blockSignals(True)
        self.projects_filter_owner.blockSignals(True)
        self.projects_filter_structures.blockSignals(True)
        self.projects_filter_id.blockSignals(True)
        
        self.projects_filter_name.clear()
        self.projects_filter_owner.clear()
        self.projects_filter_structures.clear()
        self.projects_filter_id.clear()
        
        # Unblock signals
        self.projects_filter_name.blockSignals(False)
        self.projects_filter_owner.blockSignals(False)
        self.projects_filter_structures.blockSignals(False)
        self.projects_filter_id.blockSignals(False)
        
        # Reapply to show all projects
        self.apply_projects_filters()
    
    def apply_projects_filters(self):
        """Apply column filters to the projects table"""
        if not hasattr(self, 'projects_data') or not self.projects_data:
            return
        
        # Get filter values
        filter_name = self.projects_filter_name.text().strip().lower()
        filter_owner = self.projects_filter_owner.text().strip().lower()
        filter_structures = self.projects_filter_structures.text().strip()
        filter_id = self.projects_filter_id.text().strip().lower()
        
        # Parse structures filter (supports >, <, >=, <=, =, or range)
        struct_min, struct_max, struct_operator = self.parse_resolution_filter(filter_structures)
        
        # Filter projects
        filtered_projects = []
        for project in self.projects_data:
            # Project name
            project_name = str(project.get('project_label', '')).lower()
            
            # Owner
            owner = ''
            for field in ['owner', 'project_owner', 'created_by', 'owner_username', 'creator', 'author', 'username']:
                if project.get(field):
                    owner = str(project.get(field)).lower()
                    break
            
            # Structures count
            structures_count = project.get('count_structures_in_project', 0)
            
            # Project ID
            project_id = str(project.get('project_id', '')).lower()
            
            # Text filters (case-insensitive contains)
            if filter_name and filter_name not in project_name:
                continue
            if filter_owner and filter_owner not in owner:
                continue
            if filter_id and filter_id not in project_id:
                continue
            
            # Numeric filter for structures count
            if filter_structures:
                if not self.check_resolution_filter(structures_count, struct_min, struct_max, struct_operator):
                    continue
            
            filtered_projects.append(project)
        
        # Update table with filtered results
        self.projects_table.setSortingEnabled(False)
        self.projects_table.setRowCount(len(filtered_projects))
        
        for row, project in enumerate(filtered_projects):
            # Project Name
            name_item = QTableWidgetItem(project.get('project_label', ''))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setData(Qt.UserRole, project)
            self.projects_table.setItem(row, 0, name_item)
            
            # Owner
            owner = ''
            for field in ['owner', 'project_owner', 'created_by', 'owner_username', 'creator', 'author', 'username']:
                if project.get(field):
                    owner = project.get(field)
                    break
            
            owner_item = QTableWidgetItem(str(owner))
            owner_item.setFlags(owner_item.flags() & ~Qt.ItemIsEditable)
            self.projects_table.setItem(row, 1, owner_item)
            
            # Structures count
            count = project.get('count_structures_in_project', 0)
            count_item = NumericTableWidgetItem(str(count), count)
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            self.projects_table.setItem(row, 2, count_item)
            
            # Project ID
            id_item = QTableWidgetItem(str(project.get('project_id', '')))
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.projects_table.setItem(row, 3, id_item)
        
        self.projects_table.setSortingEnabled(True)
    
    def clear_project_filters(self):
        """Clear all project structure filter inputs without triggering filtering"""
        # Block signals to prevent triggering apply_project_filters while clearing
        self.project_filter_external_code.blockSignals(True)
        self.project_filter_label.blockSignals(True)
        self.project_filter_title.blockSignals(True)
        self.project_filter_method.blockSignals(True)
        
        self.project_filter_external_code.clear()
        self.project_filter_label.clear()
        self.project_filter_title.clear()
        self.project_filter_method.clear()
        
        # Unblock signals
        self.project_filter_external_code.blockSignals(False)
        self.project_filter_label.blockSignals(False)
        self.project_filter_title.blockSignals(False)
        self.project_filter_method.blockSignals(False)
        
        # Reapply to show all structures
        self.apply_project_filters()
    
    def apply_project_filters(self):
        """Apply column filters to the project structures table"""
        if not hasattr(self, 'current_project_structures') or not self.current_project_structures:
            return
        
        # Get filter values
        filter_ext_code = self.project_filter_external_code.text().strip().lower()
        filter_lbl = self.project_filter_label.text().strip().lower()
        filter_ttl = self.project_filter_title.text().strip().lower()
        filter_mth = self.project_filter_method.text().strip().lower()
        
        # Filter structures
        filtered_structures = []
        for structure in self.current_project_structures:
            # Use the same field extraction logic as populate_project_structures_table
            external_code = (structure.get('EXTERNAL_CODE') or 
                           structure.get('external_code') or 
                           structure.get('general', {}).get('external_code', 'N/A'))
            
            label = (structure.get('LABEL') or 
                    structure.get('label') or 
                    structure.get('PROJECT_LABEL') or 
                    structure.get('project_label') or
                    structure.get('general', {}).get('label', external_code))
            
            title = (structure.get('TITLE') or 
                    structure.get('title') or 
                    structure.get('general', {}).get('title', external_code))
            
            method = (structure.get('METHOD') or 
                     structure.get('method') or 
                     structure.get('general', {}).get('method', 'N/A'))
            
            # Convert to lowercase for comparison (handle None values)
            external_code_lower = str(external_code).lower() if external_code else ''
            label_lower = str(label).lower() if label else ''
            title_lower = str(title).lower() if title else ''
            method_lower = str(method).lower() if method else ''
            
            # Text filters (case-insensitive contains)
            if filter_ext_code and filter_ext_code not in external_code_lower:
                continue
            if filter_lbl and filter_lbl not in label_lower:
                continue
            if filter_ttl and filter_ttl not in title_lower:
                continue
            if filter_mth and filter_mth not in method_lower:
                continue
            
            filtered_structures.append(structure)
        
        # Update table with filtered results
        self.populate_project_structures_table(filtered_structures)
        
    def load_selected_structures(self):
        """Load selected structures into PyMOL"""
        selected_structures = []
        
        selected_rows = self.results_table.selectionModel().selectedRows()
        log_debug(f"Found {len(selected_rows)} selected rows in search results")
        
        for index in selected_rows:
            row = index.row()
            item = self.results_table.item(row, 0)
            if item:
                structure_id = item.data(Qt.UserRole)
                external_code = item.text()
                log_debug(f"Row {row}: structure_id={structure_id}, external_code={external_code}")
                
                if structure_id:
                    selected_structures.append({
                        'structure_id': str(structure_id),
                        'external_code': external_code
                    })
                else:
                    log_error(f"Row {row}: structure_id is None!")
                    
        if not selected_structures:
            QMessageBox.warning(self, "Warning", "Please select at least one structure to load")
            return
            
        # Start loading in background thread
        self.load_thread = LoadStructureThread(self.api_client, selected_structures)
        self.load_thread.structure_loaded.connect(self.handle_structure_loaded)
        self.load_thread.error_occurred.connect(self.handle_load_error)
        self.load_thread.status_update.connect(self.update_status)
        self.load_thread.all_structures_loaded.connect(self.handle_all_structures_loaded)
        
        self.load_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.load_thread.start()
        
    def handle_structure_loaded(self, structure_id: str, object_name: str):
        """Handle successful structure loading"""
        log_info(f"Loaded structure {structure_id} as {object_name}")
        
    def handle_all_structures_loaded(self):
        """Handle completion of all structure loading"""
        self.progress_bar.setVisible(False)
        self.load_button.setEnabled(True)
        # Re-enable project structures load button if it exists
        if hasattr(self, 'load_project_structures_button'):
            self.load_project_structures_button.setEnabled(True)
        self.check_login_status()  # Restore login status
        
    def handle_load_error(self, error_message: str):
        """Handle structure loading errors"""
        self.progress_bar.setVisible(False)
        self.load_button.setEnabled(True)
        # Re-enable project structures load button if it exists
        if hasattr(self, 'load_project_structures_button'):
            self.load_project_structures_button.setEnabled(True)
        QMessageBox.critical(self, "Load Error", error_message)
        
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Clean up threads
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.terminate()
            self.search_thread.wait()
            
        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.terminate()
            self.load_thread.wait()
            
        event.accept()
