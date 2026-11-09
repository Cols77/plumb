"""Offline subprocess probe for Hermes' real plugin skill registry."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    plugin_dir = Path(sys.argv[1])
    from hermes_cli import plugins
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from tools.skills_tool import skill_view

    manager = PluginManager()
    plugins._plugin_manager = manager
    manifest = PluginManifest(name="iaso", source="project", path=str(plugin_dir))
    context = PluginContext(manifest, manager)
    spec = importlib.util.spec_from_file_location("probe_iaso_plugin", plugin_dir / "plugin.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.register(context)
    result = {
        "registered": sorted(manager._plugin_skills),
        "iaso": json.loads(skill_view("iaso:iaso-records", preprocess=False)),
        "clarify": json.loads(skill_view("iaso:iaso-clarify", preprocess=False)),
        "flat": json.loads(skill_view("iaso" , preprocess=False)),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
