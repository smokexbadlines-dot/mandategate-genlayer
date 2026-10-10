"""RPC smoke test for GLSim or Studio; enable with MANDATEGATE_RUN_INTEGRATION=1."""

import json
import os

import pytest
import requests
from genlayer_py import create_client
from genlayer_py.chains import localnet

from consumer.merge_consumer import execute_merge, prepare_merge
from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded


pytestmark = pytest.mark.skipif(
    os.environ.get("MANDATEGATE_RUN_INTEGRATION") != "1",
    reason="Set MANDATEGATE_RUN_INTEGRATION=1 and start GenLayer RPC",
)


def test_open_close_gate_over_rpc():
    factory = get_contract_factory(contract_file_path="mandate_gate.py")
    contract = factory.deploy()
    account = get_default_account()
    receipt = contract.open_gate(args=[
        "octocat", "widgets", 7, "main", "Add parser in src/widget.py",
        json.dumps(["src/widget.py"]), account.address,
    ]).transact()
    assert tx_execution_succeeded(receipt)
    gate = contract.get_gate(args=["1"]).call()
    assert gate["repo"] == "octocat/widgets"
    assert gate["verdict"] == "NOT_REVIEWED"
    assert gate["is_open"] is True
    receipt = contract.close_gate(args=["1"]).transact()
    assert tx_execution_succeeded(receipt)
    assert contract.get_gate(args=["1"]).call()["is_open"] is False


@pytest.mark.skipif(os.environ.get("MANDATEGATE_RUN_SIM") != "1",
                    reason="Requires GLSim mock RPC")
def test_review_and_spend_over_simulator():
    head = "a" * 40
    base = "b" * 40
    patch = "@@ -0,0 +1,2 @@\n+def parse_widget(value):\n+    return value\n"
    pr = {
        "number": 7, "state": "open", "draft": False, "merged": False,
        "commits": 1, "changed_files": 1, "additions": 2, "deletions": 0,
        "head": {"sha": head, "repo": {"full_name": "octocat/widgets"}},
        "base": {"sha": base, "ref": "main", "repo": {"full_name": "octocat/widgets"}},
    }
    commit = {
        "sha": head, "parents": [{"sha": base}],
        "stats": {"total": 2, "additions": 2, "deletions": 0},
        "files": [{"filename": "src/widget.py", "status": "added", "additions": 2,
                   "deletions": 0, "changes": 2, "patch": patch}],
    }
    answer = {"files": [{"path": "src/widget.py", "grade": "IN_SCOPE",
                         "mandate_quote": "Add widget parser",
                         "patch_quote": "+def parse_widget"}]}
    rpc = requests.post("http://127.0.0.1:4000/api", json={
        "jsonrpc": "2.0", "id": 1, "method": "sim_installMocks",
        "params": {
            "strict": True,
            "web_mocks": {
                r"api\.github\.com/repos/octocat/widgets/pulls/7": {"status": 200, "body": json.dumps(pr)},
                r"api\.github\.com/repos/octocat/widgets/commits/": {"status": 200, "body": json.dumps(commit)},
            },
            "llm_mocks": {r"Assess whether each changed file": json.dumps(answer)},
        },
    }, timeout=10)
    rpc.raise_for_status()
    assert "error" not in rpc.json()

    factory = get_contract_factory(contract_file_path="mandate_gate.py")
    contract = factory.deploy()
    account = get_default_account()
    receipt = contract.open_gate(args=[
        "octocat", "widgets", 7, "main", "Add widget parser in src/widget.py.",
        json.dumps(["src/widget.py"]), account.address,
    ]).transact()
    assert tx_execution_succeeded(receipt)
    receipt = contract.review_pr(args=["1", head]).transact()
    assert tx_execution_succeeded(receipt)
    gate = contract.get_gate(args=["1"]).call()
    assert gate["verdict"] == "AUTHORIZED"
    assert contract.can_consume(args=["1", head, 1]).call() is True

    class FakeResponse:
        def __init__(self, value):
            self.value = value

        def raise_for_status(self):
            pass

        def json(self):
            return self.value

    class FakeGitHub:
        merged = False

        def get(self, url, timeout):
            return FakeResponse(pr)

        def put(self, url, json, timeout):
            assert json["sha"] == head
            self.merged = True
            return FakeResponse({"merged": True})

    github = FakeGitHub()
    client = create_client(chain=localnet, account=account)
    plan = prepare_merge(client, github, contract.address, "1", "octocat/widgets", 7,
                         account.address)
    tx_id = execute_merge(client, account, github, contract.address, plan)
    assert tx_id
    assert github.merged
    assert contract.can_consume(args=["1", head, 1]).call() is False
