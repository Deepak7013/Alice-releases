"""Validation-first plugin loader.

Loading imports a declared entrypoint only after the plugin is registered and
enabled. It does not execute installation commands or bypass Alice policy.
"""
from __future__ import annotations
import importlib, inspect
from .registry import PluginRegistry, PluginValidationError

class PluginLoader:
    def __init__(self, registry: PluginRegistry): self.registry=registry

    def health_check(self, name):
        manifest=self.registry.get(name)
        if not manifest: return {'ok':False,'status':'unknown_plugin'}
        if not manifest.enabled: return {'ok':False,'status':'disabled'}
        try:
            module_name, func_name=manifest.entrypoint.split(':',1)
            mod=importlib.import_module(module_name)
            fn=getattr(mod,func_name)
            if not callable(fn): raise TypeError('Entrypoint is not callable')
            return {'ok':True,'status':'healthy','entrypoint':manifest.entrypoint}
        except Exception as e:
            return {'ok':False,'status':'unhealthy','error':str(e)[:500]}

    def load(self,name):
        manifest=self.registry.get(name)
        if not manifest: raise KeyError(name)
        if not manifest.enabled: raise PluginValidationError('Plugin is disabled')
        health=self.health_check(name)
        if not health['ok']: raise PluginValidationError('Plugin health check failed: '+health.get('error',health['status']))
        module_name, func_name=manifest.entrypoint.split(':',1)
        fn=getattr(importlib.import_module(module_name),func_name)
        return fn
