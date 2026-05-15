from __future__ import annotations

import shutil


def javascript_runtime_options() -> dict[str, dict[str, str]]:
    if deno_path := shutil.which("deno"):
        return {"deno": {"path": deno_path}}
    if node_path := shutil.which("node"):
        return {"node": {"path": node_path}}
    return {}

