"""Dependency acquisition for self-building.

Only named PyPI packages are accepted; installation always requires explicit
permission through the host terminal permission manager.
"""
import re, subprocess, sys
class DependencyManager:
    def __init__(self, permission=None): self.permission=permission
    def install(self, package, version='', timeout=180):
        package=str(package).strip(); version=str(version).strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',package): raise ValueError('Invalid PyPI package name')
        if version and not re.fullmatch(r'[A-Za-z0-9_.!<>=~*+,-]{1,60}',version): raise ValueError('Invalid package version')
        spec=package+(version if version.startswith(('=','>','<','~')) else ('=='+version if version else ''))
        cmd=f'"{sys.executable}" -m pip install {spec}'
        if self.permission and not self.permission(cmd): return {'ok':False,'status':'denied','package':package}
        p=subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=int(timeout))
        return {'ok':p.returncode==0,'package':package,'stdout':p.stdout[-5000:],'stderr':p.stderr[-5000:]}
