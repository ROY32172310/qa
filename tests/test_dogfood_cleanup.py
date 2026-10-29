from __future__ import annotations

import os
import subprocess

import pytest

from dogfood import run


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group cleanup")
def test_process_tree_cleanup_is_idempotent_after_group_disappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_group(_pid: int, _signal: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(run.os, "killpg", missing_group, raising=False)
    process = subprocess.Popen(["true"])
    run._terminate_process_tree(process)

    assert process.returncode is not None
