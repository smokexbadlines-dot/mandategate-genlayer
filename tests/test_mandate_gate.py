"""Direct-mode contract tests with deterministic GitHub and model responses."""

import json


HEAD = "a" * 40
BASE = "b" * 40
MANDATE = "Add widget parser in src/widget.py."
PATCH = "@@ -0,0 +1,2 @@\n+def parse_widget(value):\n+    return value\n"


def github_mocks(vm, path="src/widget.py", patch=PATCH, additions=2, count=1,
                 previous_path=""):
    pr = {
        "number": 7, "state": "open", "draft": False, "merged": False, "commits": 1,
        "head": {"sha": HEAD, "repo": {"full_name": "octocat/widgets"}},
        "base": {"sha": BASE, "ref": "main", "repo": {"full_name": "octocat/widgets"}},
        "changed_files": count,
        "additions": additions, "deletions": 0,
    }
    commit = {
        "sha": HEAD, "parents": [{"sha": BASE}],
        "stats": {"total": 2, "additions": 2, "deletions": 0},
        "files": [{"filename": path, "status": "renamed" if previous_path else "added",
                   "previous_filename": previous_path, "additions": 2,
                   "deletions": 0, "changes": 2, "patch": patch}],
    }
    vm.mock_web(r"api\.github\.com/repos/octocat/widgets/pulls/7", {"status": 200, "body": json.dumps(pr)})
    vm.mock_web(r"api\.github\.com/repos/octocat/widgets/commits/", {"status": 200, "body": json.dumps(commit)})


def model_mock(vm, path="src/widget.py", grade="IN_SCOPE", mandate_quote="Add widget parser"):
    answer = {"files": [{"path": path, "grade": grade,
                         "mandate_quote": mandate_quote, "patch_quote": "+def parse_widget"}]}
    vm.mock_llm(r"Assess whether each changed file", json.dumps(answer))


def deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob, mandate=MANDATE, rules=None):
    contract = direct_deploy("contracts/mandate_gate.py")
    direct_vm.sender = direct_alice
    gate_id = contract.open_gate("octocat", "widgets", 7, "main", mandate,
                                 json.dumps(rules or ["src/"]), "0x" + direct_bob.hex())
    return contract, gate_id


def test_authorized_review_single_use_ticket(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm)
    model_mock(direct_vm)
    assert contract.review_pr(gate_id, HEAD) == "AUTHORIZED"
    assert contract.can_consume(gate_id, HEAD, 1)
    assert not contract.can_consume(gate_id, BASE, 1)
    with direct_vm.expect_revert("Only the named consumer"):
        contract.consume_ticket(gate_id, HEAD, 1)
    direct_vm.sender = direct_bob
    assert contract.consume_ticket(gate_id, HEAD, 1)
    assert not contract.can_consume(gate_id, HEAD, 1)
    assert not contract.get_gate(gate_id)["is_open"]
    with direct_vm.expect_revert("Ticket is unavailable"):
        contract.consume_ticket(gate_id, HEAD, 1)
    with direct_vm.expect_revert("Gate is closed or missing"):
        contract.review_pr(gate_id, HEAD)


def test_disallowed_file_never_gets_ticket(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm, path="admin/secrets.py")
    model_mock(direct_vm, path="admin/secrets.py")
    assert contract.review_pr(gate_id, HEAD) == "OUT_OF_SCOPE"
    assert contract.get_report(gate_id)["out_of_scope"] == ["admin/secrets.py"]
    assert not contract.can_consume(gate_id, HEAD, 1)


def test_sensitive_file_needs_literal_mandate_path(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob,
                                     rules=[".github/workflows/"])
    github_mocks(direct_vm, path=".github/workflows/release.yml")
    model_mock(direct_vm, path=".github/workflows/release.yml")
    assert contract.review_pr(gate_id, HEAD) == "OUT_OF_SCOPE"
    assert not contract.can_consume(gate_id, HEAD, 1)


def test_incomplete_commit_evidence_is_unverified(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm, count=2)
    assert contract.review_pr(gate_id, HEAD) == "UNVERIFIED"
    assert contract.get_report(gate_id)["reason"] == "COMMIT_IDENTITY_OR_TOTALS"
    assert not contract.can_consume(gate_id, HEAD, 1)


def test_missing_patch_quote_needs_review(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm)
    model_mock(direct_vm, mandate_quote="not in the mandate")
    assert contract.review_pr(gate_id, HEAD) == "NEEDS_REVIEW"
    assert not contract.can_consume(gate_id, HEAD, 1)


def test_close_gate_revokes_ticket(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm)
    model_mock(direct_vm)
    contract.review_pr(gate_id, HEAD)
    contract.close_gate(gate_id)
    assert not contract.can_consume(gate_id, HEAD, 1)


def test_truncated_patch_is_unverified(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm, patch="@@ -0,0 +1,2 @@\n+def parse_widget(value):\n")
    assert contract.review_pr(gate_id, HEAD) == "UNVERIFIED"
    assert contract.get_report(gate_id)["reason"] == "PATCH_TOTALS"


def test_renamed_old_path_must_be_allowed(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm, previous_path="admin/secret.py")
    model_mock(direct_vm)
    assert contract.review_pr(gate_id, HEAD) == "OUT_OF_SCOPE"
    assert not contract.can_consume(gate_id, HEAD, 1)


def test_validator_independently_rejects_different_verdict(
    direct_vm, direct_deploy, direct_alice, direct_bob,
):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    github_mocks(direct_vm)
    model_mock(direct_vm)
    assert contract.review_pr(gate_id, HEAD) == "AUTHORIZED"
    direct_vm.clear_mocks()
    github_mocks(direct_vm)
    model_mock(direct_vm, grade="OUT_OF_SCOPE")
    assert direct_vm.run_validator() is False


def test_stranger_cannot_replace_review(direct_vm, direct_deploy, direct_alice,
                                        direct_bob, direct_charlie):
    contract, gate_id = deploy_gate(direct_vm, direct_deploy, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only the authorizer or consumer"):
        contract.review_pr(gate_id, HEAD)
