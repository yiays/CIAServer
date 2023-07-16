"""
    Builds a windows executable from the source code
"""

from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need fine tuning.
buildOptions = dict(packages = ['asyncio','idna','aiohttp','appdirs','packaging'], excludes = [])

executables = [
    Executable('main.py', base='Console', targetName = 'CIAServer.exe')
]

setup(name='CIAServer.exe',
      version = '1.2',
      description = 'Serve your cia and 3dsx files directly to FBI via remote install',
      options = dict(build_exe = buildOptions),
      executables = executables)
