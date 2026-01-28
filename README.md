# 3decision PyMOL Plugin

A plugin to search and load structures from 3decision database into PyMOL.

## Installation

### Download

1. Go to the [Releases page](https://github.com/Discngine/3decision_plugin_pymol/releases/latest)
2. Download `3decision_plugin_pymol.zip`

### Install in PyMOL

1. Open PyMOL
2. Go to **Plugin → Plugin Manager**
3. Click on the **Install New Plugin** tab
4. Click **Choose file...** and select the downloaded ZIP file
5. Restart PyMOL

## Usage

After installation, access the plugin via:
- **Menu**: Plugin → 3decision

## Development

### Building the ZIP package

To create a distributable ZIP file for the plugin:

```bash
cd 3decision_plugin_pymol
zip -r tmp/3decision_plugin_pymol_test.zip . -x "*.pyc" -x "__pycache__/*" -x "*.git*" -x "tmp/*"
```

This excludes compiled Python files, cache directories, git files, and temporary files.