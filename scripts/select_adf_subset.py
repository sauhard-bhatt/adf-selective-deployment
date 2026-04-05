import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Set, Tuple, List
from collections import defaultdict

# Your repo layout has pipeline/, dataset/, linkedService/ at ROOT.
REPO_ROOT = Path(".")
STAGE_ROOT = Path("build/adf_subset")

RESOURCE_DIRS = {
    "pipeline": REPO_ROOT / "pipeline",
    "dataset": REPO_ROOT / "dataset",
    "linkedService": REPO_ROOT / "linkedService",
    "dataflow": REPO_ROOT / "dataflow",
    "trigger": REPO_ROOT / "trigger",
    "integrationRuntime": REPO_ROOT / "integrationRuntime",
    "credential": REPO_ROOT / "credential",
    "managedVirtualNetwork": REPO_ROOT / "managedVirtualNetwork",
}

# Copy these if present so ADF utilities behave the same on staged subset.
ROOT_FILES_TO_COPY = [
    "publish_config.json",
    "arm-template-parameters-definition.json",
    "arm_template_parameters-definition.json",
    "package.json",
    "package-lock.json",
]

# Global parameters directory
GLOBAL_PARAMS_DIR = REPO_ROOT / "globalParameters"

def read_json(p: Path) -> Dict:
    """Read and parse JSON file."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON in {p}: {e}")
        raise
    except Exception as e:
        print(f"[ERROR] Failed to read {p}: {e}")
        raise

def write_json(p: Path, obj: Dict) -> None:
    """Write object as formatted JSON."""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")

def find_resource_file(kind: str, name: str) -> Path:
    """Find resource file path by kind and name."""
    d = RESOURCE_DIRS.get(kind)
    if not d:
        raise ValueError(f"Unknown resource kind: {kind}")
    return d / f"{name}.json"

def discover_refs_safe(obj, refs: Dict[str, Set[str]], path: str = "root") -> None:
    """
    Recursively walk JSON structure to discover all resource references.
    This is more robust than regex as it handles multi-line formatting,
    nested structures, and provides warnings for dynamic references.
    """
    if isinstance(obj, dict):
        # Check for reference patterns
        if "type" in obj and "referenceName" in obj:
            ref_type = obj.get("type", "")
            ref_name = obj.get("referenceName", "")
            
            # Only capture literal strings, warn on expressions
            if isinstance(ref_name, str) and ref_name:
                if ref_name.startswith("@"):
                    # Dynamic reference - cannot resolve statically
                    print(f"[WARN] Dynamic reference at {path}: {ref_name} (type: {ref_type})")
                    print(f"       This dependency cannot be resolved automatically.")
                    refs["dynamic_refs"].add(f"{ref_type}:{ref_name}")
                else:
                    # Static reference - add to appropriate set
                    if "DatasetReference" in ref_type:
                        refs["datasets"].add(ref_name)
                    elif "LinkedServiceReference" in ref_type:
                        refs["linkedServices"].add(ref_name)
                    elif "DataFlowReference" in ref_type:
                        refs["dataflows"].add(ref_name)
                    elif "PipelineReference" in ref_type:
                        refs["pipelines"].add(ref_name)
                    elif "IntegrationRuntimeReference" in ref_type:
                        refs["integrationRuntimes"].add(ref_name)
                    elif "CredentialReference" in ref_type:
                        refs["credentials"].add(ref_name)
        
        # Check for linked service in dataset definition
        if "linkedServiceName" in obj:
            ls_obj = obj["linkedServiceName"]
            if isinstance(ls_obj, dict) and "referenceName" in ls_obj:
                ls_name = ls_obj["referenceName"]
                if isinstance(ls_name, str) and ls_name and not ls_name.startswith("@"):
                    refs["linkedServices"].add(ls_name)
        
        # Check for compute reference in dataflows
        if "computeType" in obj or "compute" in obj:
            compute = obj.get("compute", {})
            if isinstance(compute, dict) and "computeType" in compute:
                compute_ref = compute.get("referenceName")
                if compute_ref and not str(compute_ref).startswith("@").
                    refs["integrationRuntimes"].add(compute_ref)
        
        # Recurse into nested objects
        for key, value in obj.items():
            discover_refs_safe(value, refs, f"{path}.{key}")
    
elif isinstance(obj, list):
        # Recurse into list items
        for i, item in enumerate(obj):
            discover_refs_safe(item, refs, f"{path}[{i}]")

def discover_refs_regex_fallback(obj: Dict) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    """
    Fallback regex-based discovery (kept for backward compatibility).
    Now also discovers pipeline references.
    """
    s = json.dumps(obj)

    datasets = set(re.findall(r'"type"\s*:\s*"DatasetReference"\s*,\s*"referenceName"\s*:\s*"([^\