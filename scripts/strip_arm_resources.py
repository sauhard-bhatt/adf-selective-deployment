#!/usr/bin/env python3
"""
Strip selected resource types from an exported ADF ARM template before deployment,
and CLEAN UP dependsOn references that point to stripped resources.

Typical use:
  python3 scripts/strip_arm_resources.py \
    --in artifacts/ARMTemplateForFactory.json \
    --out artifacts/ARMTemplateForFactory.safe.json \
    --strip-type Microsoft.DataFactory/factories/linkedServices \
    --strip-type Microsoft.DataFactory/factories/managedVirtualNetworks \
    --strip-type Microsoft.DataFactory/factories/managedVirtualNetworks/managedPrivateEndpoints \
    --strip-type Microsoft.DataFactory/factories/globalparameters \
    --strip-type Microsoft.DataFactory/factories/credentials \
    --strip-type Microsoft.DataFactory/factories/integrationRuntimes

Optional:
  --strip-unused-parameters   (removes parameters not referenced in template)
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any


def normalize(t: str) -> str:
    return (t or "").strip().lower()


def collect_used_parameters(template: dict) -> Set[str]:
    """
    Scan ARM template JSON for parameter references like:
      [parameters('paramName')]
    """
    used = set()
    text = json.dumps(template)
    pattern = re.compile(r"parameters\('([^']+)'\)", re.IGNORECASE)
    for match in pattern.findall(text):
        used.add(match)
    return used


def token_from_arm_type(arm_type: str) -> str:
    """
    Convert ARM type to a path-ish token that appears in dependsOn/resourceId strings.
    Example:
      Microsoft.DataFactory/factories/linkedServices -> linkedservices
    """
    parts = (arm_type or "").split("/")
    if not parts:
        return ""
    return normalize(parts[-1])


def extract_leaf_name(name_expr: str) -> str:
    """
    Try to extract the last segment of an ADF resource name expression.

    Examples:
      "[concat(parameters('factoryName'), '/dd_di_interfaces_akv_ls')]"
        -> "dd_di_interfaces_akv_ls"

      "dd-nonprd-wus-hub-adf/SomePipeline"
        -> "somepipeline" (normalized)

    This is best-effort; if it can't extract, returns "".
    """
    if not name_expr:
        return ""
    s = str(name_expr).strip()

    # If it looks like concat(..., '/X')] capture X (until quote/bracket)
    m = re.search(r"/([^'/\]]+)'\)\]$", s)
    if m:
        return normalize(m.group(1))

    # If it's a plain "factory/x" style string
    if "/" in s and "concat(" not in s.lower():
        return normalize(s.split("/")[-1])

    return ""


def depends_on_points_to_stripped(dep: str, stripped_tokens: Set[str], stripped_leaf_names: Set[str]) -> bool:
    """
    Determine if a dependsOn string points to a stripped resource.
    We primarily key off the stripped token (linkedservices, integrationruntimes, etc.)
    AND (when possible) a leaf-name match.

    This avoids accidentally removing unrelated dependsOn edges.
    """
    if not dep:
        return False

    d = normalize(dep)

    # must mention one of the stripped tokens in typical ADF patterns
    # patterns seen: "...factories/linkedServices..." OR "/linkedServices/" OR "linkedServices" in resourceId(...)
    token_hit = None
    for tok in stripped_tokens:
        if not tok:
            continue
        if f"/{tok}" in d or f"factories/{tok}" in d or f"'{tok}'" in d or f"\"{tok}\"" in d:
            token_hit = tok
            break

    if not token_hit:
        return False

    # Prefer confirming with a leaf-name match when we have it
    if stripped_leaf_names:
        for leaf in stripped_leaf_names:
            if leaf and leaf in d:
                return True

        # If we couldn't match leaf names, still allow removal when it clearly references factoryName
        # and the token is present (typical ADF generated templates)
        if "parameters('factoryname')" in d or "parameters(\"factoryname\")" in d:
            return True

        return False

    # If we have no leaf names, fall back to token match + factoryName reference
    return ("parameters('factoryname')" in d) or ("parameters(\"factoryname\")" in d)


def clean_depends_on_in_resource(res: Dict[str, Any], stripped_tokens: Set[str], stripped_leaf_names: Set[str]) -> int:
    """
    Remove dependsOn entries referencing stripped resources from a single resource.
    Returns number of dependsOn entries removed.
    """
    removed_count = 0

    dep = res.get("dependsOn")
    if isinstance(dep, list):
        cleaned = []
        for d in dep:
            if isinstance(d, str) and depends_on_points_to_stripped(d, stripped_tokens, stripped_leaf_names):
                removed_count += 1
            else:
                cleaned.append(d)
        res["dependsOn"] = cleaned

    # Recurse into nested resources if present
    nested = res.get("resources")
    if isinstance(nested, list):
        for child in nested:
            if isinstance(child, dict):
                removed_count += clean_depends_on_in_resource(child, stripped_tokens, stripped_leaf_names)

    return removed_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", dest="out_path", required=True)
    parser.add_argument(
        "--strip-type",
        action="append",
        default=[],
        help="ARM resource type to remove (can repeat)",
    )
    parser.add_argument(
        "--strip-unused-parameters",
        action="store_true",
        help="Remove parameters not referenced after stripping",
    )

    args = parser.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    if not in_path.exists():
        raise SystemExit(f"Input file not found: {in_path}")

    arm = json.loads(in_path.read_text(encoding="utf-8"))

    if "resources" not in arm or not isinstance(arm["resources"], list):
        raise SystemExit("Invalid ARM template: no resources array")

    strip_types = {normalize(t) for t in args.strip_type}
    if not strip_types:
        raise SystemExit("No --strip-type specified")

    # Tokens used to detect dependsOn references
    stripped_tokens = {token_from_arm_type(t) for t in strip_types}

    original_count = len(arm["resources"])
    kept: List[Dict[str, Any]] = []
    removed: List[Tuple[str, str]] = []  # (type, name)

    for r in arm["resources"]:
        rtype = normalize(r.get("type", ""))
        rname = str(r.get("name", "<unnamed>"))
        if rtype in strip_types:
            removed.append((rtype, rname))
        else:
            kept.append(r)

    arm["resources"] = kept

    stripped_leaf_names = set()
    for (_t, n) in removed:
        leaf = extract_leaf_name(n)
        if leaf:
            stripped_leaf_names.add(leaf)

    # Clean dependsOn in kept resources
    depends_removed_total = 0
    for r in arm["resources"]:
        depends_removed_total += clean_depends_on_in_resource(r, stripped_tokens, stripped_leaf_names)

    print("--------------------------------------------------")
    print(f"Original resource count: {original_count}")
    print(f"Removed resource count : {len(removed)}")
    print(f"Kept resource count    : {len(kept)}")
    if removed:
        print("Removed resource names (first 20):")
        for (_t, name) in removed[:20]:
            print(f"  - {name}")
    print("--------------------------------------------------")
    print(f"dependsOn entries removed (referencing stripped types): {depends_removed_total}")
    print("--------------------------------------------------")

    # Optional: strip unused parameters
    if args.strip_unused_parameters and "parameters" in arm and isinstance(arm["parameters"], dict):
        used_params = collect_used_parameters(arm)
        original_params = set(arm["parameters"].keys())
        new_params = {k: v for k, v in arm["parameters"].items() if k in used_params}
        removed_params = original_params - set(new_params.keys())
        arm["parameters"] = new_params

        print(f"Original parameter count: {len(original_params)}")
        print(f"Removed unused parameters: {len(removed_params)}")
        if removed_params:
            print("Removed parameter names (first 20):")
            for name in list(sorted(removed_params))[:20]:
                print(f"  - {name}")
        print("--------------------------------------------------")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(arm, indent=2), encoding="utf-8")

    print(f"[OK] Safe template written to: {out_path}")


if __name__ == "__main__":
    main()
