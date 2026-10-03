"""Validate generated systemd configuration, beyond shell syntax."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import shlex


def test_generated_service_is_accepted_by_systemd(tmp_path):
    root = Path(__file__).resolve().parent.parent
    mock_bin = tmp_path / 'bin'
    mock_bin.mkdir()
    for command in ('uv', 'systemctl'):
        script = mock_bin / command
        script.write_text('#!/bin/sh\nexit 0\n')
        script.chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path), PATH=str(mock_bin) + ':' + os.environ['PATH'])
    runtime_python = tmp_path / '.local/share/simple-recipes/runtime/bin/python'
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    runtime_python.chmod(0o755)
    env['RECIPES_DATA_DIR'] = str(tmp_path / 'data')
    subprocess.run(['bash', str(root / 'setup.sh')], env=env, check=True, capture_output=True, text=True)
    unit = tmp_path / '.config/systemd/user/simple-recipes.service'
    result = subprocess.run(['systemd-analyze', '--user', 'verify', str(unit)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'data/rezepte.db').exists()
