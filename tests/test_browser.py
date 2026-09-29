import pytest
from agent.tools.browser import browser_check
from agent.tools.base import ToolContext, ToolError
from agent.context import WorkingState
from agent.sandbox import SandboxResult

class Sandbox:
    def __init__(self, code=0): self.code=code; self.command=''
    def run(self, command, *args, **kwargs):
        self.command=command
        return SandboxResult('ENOTDIR' if self.code else 'ok', self.code, [])

def test_browser_collision_preserves_user_file(tmp_path):
    (tmp_path/'.krovin-browser').write_text('user data')
    sb=Sandbox()
    ctx=ToolContext(tmp_path,tmp_path,WorkingState(),sandbox=sb)
    browser_check({'path':'.'},ctx)
    assert 'mkdir -p .krovin-browser-' in sb.command
    assert (tmp_path/'.krovin-browser').read_text()=='user data'

def test_browser_failure_is_tool_failure(tmp_path):
    ctx=ToolContext(tmp_path,tmp_path,WorkingState(),sandbox=Sandbox(1))
    with pytest.raises(ToolError,match='ENOTDIR'):
        browser_check({},ctx)

def test_browser_rejects_unknown_preview(tmp_path):
    ctx=ToolContext(tmp_path,tmp_path,WorkingState(),sandbox=Sandbox())
    with pytest.raises(ToolError,match='过期'):
        browser_check({'preview_url':'http://localhost/'},ctx)
