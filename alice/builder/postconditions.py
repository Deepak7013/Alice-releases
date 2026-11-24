"""Disk-readback checks for Alice's generated project builds."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..execution.postconditions import PostconditionResult


def verify_builder_project_postcondition(args, result, projects_root, default_project_name="alice-project"):
    if not isinstance(result,dict) or result.get("ok") is not True:
        return PostconditionResult(False,{"observed":False},"builder_did_not_report_success")
    tests=result.get("tests")
    rows=tests.get("results") if isinstance(tests,dict) else None
    context=result.get("_postcondition_context")
    receipts=context.get("files") if isinstance(context,dict) else None
    if (not isinstance(tests,dict) or tests.get("ok") is not True or not isinstance(rows,list) or not rows
            or any(not isinstance(row,dict) or row.get("returncode")!=0 for row in rows)
            or any(not isinstance(row.get("sandbox"),dict) or row["sandbox"].get("verified") is not True for row in rows)
            or not isinstance(context,dict) or context.get("successful_test_count")!=len(rows)
            or not isinstance(receipts,list) or not receipts):
        return PostconditionResult(False,{"observed":False},"builder_isolated_tests_or_file_receipts_missing")
    try:
        root=Path(projects_root).resolve(strict=True)
        project=Path(result.get("project","")).resolve(strict=True)
        args=args if isinstance(args,dict) else {}
        requested=str(args.get("project_name",default_project_name) or default_project_name)
        expected_name=re.sub(r'[^A-Za-z0-9_.-]+','-',requested.strip()).strip('.-')[:80] or 'project'
        if project.parent!=root or project.name!=expected_name or not project.is_dir():
            return PostconditionResult(False,{"observed":False},"builder_project_path_outside_projects_root")
        receipt_paths={}
        for item in receipts:
            if not isinstance(item,dict):
                return PostconditionResult(False,{"observed":False},"builder_file_receipt_invalid")
            rel=Path(str(item.get("path","")))
            if not isinstance(item,dict) or rel.is_absolute() or ".." in rel.parts or not rel.parts:
                return PostconditionResult(False,{"observed":False},"builder_file_receipt_invalid")
            candidate=project/rel;probe=project
            for part in rel.parts:
                probe=probe/part
                if probe.is_symlink():
                    return PostconditionResult(False,{"observed":False},"builder_symlinked_output_rejected")
            path=candidate.resolve(strict=True)
            if project not in path.parents or not path.is_file() or rel.as_posix() in receipt_paths:
                return PostconditionResult(False,{"observed":False},"builder_output_missing_or_duplicate")
            raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            if len(raw)!=item.get("size") or digest!=item.get("sha256"):
                return PostconditionResult(False,{"observed":True,"file_hashes_match":False},"builder_output_readback_mismatch")
            receipt_paths[rel.as_posix()]=digest
        changed=result.get("changed")
        normalized_changed={Path(str(value)).as_posix() for value in changed} if isinstance(changed,list) else set()
        if not isinstance(changed,list) or normalized_changed!=set(receipt_paths):
            return PostconditionResult(False,{"observed":True,"file_hashes_match":True},"builder_changed_file_inventory_mismatch")
    except Exception as exc:
        return PostconditionResult(False,{"observed":False},f"builder_output_readback_failed:{type(exc).__name__}")
    return PostconditionResult(True,{"observed":True,"file_hashes_match":True,
        "files_verified":len(receipt_paths),"successful_tests":len(rows),"isolated_tests_verified":True},
        "builder_isolated_tests_and_outputs_independently_rehashed")
