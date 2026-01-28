"""
Settings Dialog v1.2

Configuration dialog for 3decision API settings.

Version: 1.2
"""

import os
import webbrowser

try:
    # Import from pymol.Qt - the correct way for PyMOL plugins
    from pymol.Qt import QtWidgets, QtCore, QtGui
    from pymol.Qt.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
        QLabel, QMessageBox, QFormLayout, QDialogButtonBox, QFrame, QCheckBox, QComboBox
    )
    from pymol.Qt.QtCore import Qt, QThread, pyqtSignal
    from pymol.Qt.QtGui import QPixmap
except ImportError:
    # Fallback for testing outside PyMOL
    from PyQt5 import QtWidgets, QtCore, QtGui
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, 
        QLabel, QMessageBox, QFormLayout, QDialogButtonBox, QFrame, QCheckBox, QComboBox
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QPixmap

from .api_client import ThreeDecisionAPIClient

# Simple logging functions for settings dialog
def log_debug(message):
    """Log a debug message if logging is enabled"""
    try:
        from .api_client import is_logging_enabled
        if is_logging_enabled():
            print(f"DEBUG: {message}")
    except:
        # Fallback to always print if there's an import issue
        print(f"DEBUG: {message}")


class ConnectionTestThread(QThread):
    """Thread for testing API connection"""
    test_completed = pyqtSignal(bool, str)
    
    def __init__(self, api_client: ThreeDecisionAPIClient, base_url: str, api_key: str):
        super().__init__()
        self.api_client = api_client
        self.base_url = base_url
        self.api_key = api_key
        
    def run(self):
        try:
            # Configure the client temporarily
            old_url = self.api_client.base_url
            old_key = self.api_client.api_key
            old_token = self.api_client.token
            
            self.api_client.configure(self.base_url, self.api_key)
            
            # Test connection
            success = self.api_client.test_connection()
            
            if success:
                self.test_completed.emit(True, "Connection successful!")
            else:
                self.test_completed.emit(False, "Connection failed. Please check your URL and API key.")
                
                # Restore old settings if test failed
                self.api_client.base_url = old_url
                self.api_client.api_key = old_key
                self.api_client.token = old_token
                
        except Exception as e:
            self.test_completed.emit(False, f"Connection error: {str(e)}")


class SettingsDialog(QDialog):
    """Settings dialog for configuring 3decision API"""
    
    def __init__(self, api_client: ThreeDecisionAPIClient, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.test_thread = None
        self.init_ui()
        self.load_current_settings()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("3decision API Settings v1.2")
        self.setModal(True)
        self.setMinimumSize(600, 300)
        
        # Remove the question mark from the title bar on Windows
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # Main horizontal layout
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Left side - Logo (centered vertically)
        logo_layout = QVBoxLayout()
        logo_layout.addStretch()  # Top stretch
        
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        
        # Try to load the logo image
        logo_pixmap = self.load_logo()
        if logo_pixmap:
            # Scale the logo to a reasonable size
            scaled_pixmap = logo_pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
        else:
            # Fallback text if image not found
            logo_label.setText("3decision")
            logo_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #0066cc;")
            
        logo_layout.addWidget(logo_label)
        logo_layout.addStretch()  # Bottom stretch
        
        # Grey separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("QFrame { color: #cccccc; background-color: #cccccc; }")
        separator.setFixedWidth(1)
        
        # Right side - Form layout (centered vertically)
        form_widget = QFrame()
        form_main_layout = QVBoxLayout(form_widget)
        form_main_layout.addStretch()  # Top stretch
        
        # Form layout for settings
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        
        # URL input - larger and expandable
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://your-3decision-api-url.discngine.cloud")
        self.url_input.setMinimumWidth(300)
        form_layout.addRow("3decision URL:", self.url_input)
        
        # API Key input - larger and expandable
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Your API key")
        self.api_key_input.setMinimumWidth(300)
        form_layout.addRow("API Key:", self.api_key_input)
        
        # Log events checkbox
        self.log_events_checkbox = QCheckBox("Log events")
        self.log_events_checkbox.setToolTip("Enable logging of plugin events to console")
        form_layout.addRow("", self.log_events_checkbox)
        
        # Private structure naming attribute dropdown
        self.naming_attribute_combo = QComboBox()
        self.naming_attribute_combo.addItems(["label", "title", "external_code", "internal_id"])
        self.naming_attribute_combo.setToolTip(
            "Choose which attribute to use for naming private structures when loaded into PyMOL.\n"
            "Public structures (PDB, AlphaFold, etc.) always use external_code.\n"
            "Note: internal_id requires an additional API call per structure."
        )
        form_layout.addRow("Private structure name:", self.naming_attribute_combo)
        
        form_main_layout.addLayout(form_layout)
        
        # Test connection and help button layout
        test_layout = QHBoxLayout()
        test_layout.addStretch()
        
        # Help button
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.open_help)
        self.help_button.setToolTip("Open API documentation in browser")
        test_layout.addWidget(self.help_button)
        
        # Test connection button
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self.test_connection)
        test_layout.addWidget(self.test_button)
        
        form_main_layout.addLayout(test_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        form_main_layout.addWidget(self.status_label)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal
        )
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        form_main_layout.addWidget(button_box)
        
        form_main_layout.addStretch()  # Bottom stretch
        
        # Add everything to main layout
        main_layout.addLayout(logo_layout, 0)  # Logo takes minimum space
        main_layout.addWidget(separator)
        main_layout.addWidget(form_widget, 1)  # Form takes remaining space
        
        self.setLayout(main_layout)
        
        # Adjust dialog size to content
        self.adjustSize()
        
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
            log_debug(f"Settings theme detection: background RGB({bg_color.red()}, {bg_color.green()}, {bg_color.blue()}), luminance: {luminance:.3f}, dark: {is_dark}")
            return is_dark
            
        except Exception as e:
            log_debug(f"Settings theme detection error: {e}, defaulting to light theme")
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
                    log_debug(f"Settings loaded logo: {logo_filename}")
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
                    log_debug(f"Settings loaded fallback logo: {fallback_filename}")
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
                    log_debug(f"Settings loaded final fallback logo: LogoTitle2.0.png")
                    return pixmap
                    
        log_debug("Settings: No logo found")
        return None
        
    def load_current_settings(self):
        """Load current settings into the form"""
        if self.api_client.base_url:
            self.url_input.setText(self.api_client.base_url)
        if self.api_client.api_key:
            self.api_key_input.setText(self.api_client.api_key)
            
        # Load logging setting
        from .api_client import is_logging_enabled, get_private_structure_naming_attribute
        self.log_events_checkbox.setChecked(is_logging_enabled())
        
        # Load private structure naming attribute setting
        naming_attr = get_private_structure_naming_attribute()
        index = self.naming_attribute_combo.findText(naming_attr)
        if index >= 0:
            self.naming_attribute_combo.setCurrentIndex(index)
            
    def test_connection(self):
        """Test the API connection"""
        url = self.url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a 3decision URL")
            return
            
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key")
            return
            
        # Start connection test in background thread
        self.test_thread = ConnectionTestThread(self.api_client, url, api_key)
        self.test_thread.test_completed.connect(self.handle_test_result)
        
        self.test_button.setEnabled(False)
        self.status_label.setText("Testing connection...")
        self.status_label.setStyleSheet("color: blue;")
        
        self.test_thread.start()
        
    def handle_test_result(self, success: bool, message: str):
        """Handle connection test result"""
        self.test_button.setEnabled(True)
        self.status_label.setText(message)
        
        if success:
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            
    def save_settings(self):
        """Save the settings"""
        url = self.url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a 3decision URL")
            return
            
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key")
            return
            
        # Configure and save API settings
        self.api_client.configure(url, api_key)
        self.api_client.save_config()
        
        # Save logging setting
        log_enabled = self.log_events_checkbox.isChecked()
        from .api_client import set_logging_enabled, set_private_structure_naming_attribute
        set_logging_enabled(log_enabled)
        self.api_client.save_logging_setting(log_enabled)
        
        # Save private structure naming attribute setting
        naming_attr = self.naming_attribute_combo.currentText()
        set_private_structure_naming_attribute(naming_attr)
        self.api_client.save_naming_attribute_setting(naming_attr)
        
        # Try to login
        if self.api_client.login():
            QMessageBox.information(self, "Success", "Settings saved and login successful!")
            self.accept()
        else:
            QMessageBox.warning(
                self, 
                "Warning", 
                "Settings saved but login failed. Please check your credentials."
            )
            
    def open_help(self):
        """Open API documentation in the default browser"""
        try:
            webbrowser.open("https://3decision-help.discngine.cloud/en/API/Access")
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Could not open browser: {str(e)}\n\nPlease visit manually:\nhttps://3decision-help.discngine.cloud/en/API/Access"
            )
            
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Clean up thread
        if self.test_thread and self.test_thread.isRunning():
            self.test_thread.terminate()
            self.test_thread.wait()
            
        event.accept()
