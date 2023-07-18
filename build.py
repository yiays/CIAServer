"""
    Builds a windows executable from the source code
"""

from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need fine tuning.
buildOptions = {
    'packages': [],
    'includes': [],
    'excludes': []
}

executables = [
    Executable('main.py', base='Console', target_name = 'CIAServer.exe')
]

setup(name='CIAServer.exe',
      version = '1.2',
      description = 'Serve your cia and 3dsx files directly to FBI via remote install',
      options = {'build_exe': buildOptions},
      executables = executables)
