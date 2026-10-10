# MandateGate

MandateGate is a native GenLayer intelligent contract that asks: **does a proposed pull request stay inside the task a human authorized?** The authorizer pins a GitHub repository, PR number, base branch, natural-language mandate, allowed paths, and the address of the only ticket consumer. A review reads GitHub's PR and commit APIs, grades each changed file with a model, has validators independently repeat the review, and issues a single-use ticket only for an `AUTHORIZED` result.

This repository contains the contract, a GitHub merge consumer, direct tests, and an RPC integration test. The contract does not require an off-chain model service or oracle controlled by the project: GenLayer's nondeterministic web and LLM APIs run inside the contract's equivalence-principle block. The consumer is an external bridge because GitHub merges are outside GenLayer.

## Decision rules

1. The PR must be open, non-draft, from the same repository, and contain exactly **one non-merge commit**. Its sole parent must equal the current base SHA. The caller supplies the full lowercase 40-character head SHA.
2. GitHub must echo the PR number and commit SHA. PR counts, commit stats, per-file totals, and parsed patch line counts must agree. Review refuses more than 20 files, individual patches over 12,000 characters, total patches over 60,000 characters, missing patches, and ambiguous renames.
3. Every new and old path must match an authorizer-supplied exact file or directory prefix. For `.github/workflows/`, `CODEOWNERS`, `Dockerfile`, `infra/`, `terraform/`, `deploy/`, `contracts/`, and `migrations/`, the mandate must also contain the exact path.
4. The model labels each file `IN_SCOPE`, `SUPPORTING`, `UNCLEAR`, or `OUT_OF_SCOPE` and cites literal substrings from the mandate and patch. Missing citations floor a favorable grade to `UNCLEAR`; deterministic path rules floor it to `OUT_OF_SCOPE`.
5. Contract code derives `AUTHORIZED`, `NEEDS_REVIEW`, `OUT_OF_SCOPE`, or `UNVERIFIED`. Validators fetch the same GitHub evidence and independently grade every file. They require the same evidence hash, exact file and rejection sets, the same verdict, and grades within one rung.
6. Only `AUTHORIZED` opens a ticket. The ticket is bound to the gate, reviewed head SHA, and review nonce. The named consumer may spend it once while the gate is open. Spending closes the gate. The authorizer may close it earlier.

`UNVERIFIED` means the contract could not establish complete evidence; it is not an approval. Model uncertainty likewise never opens a ticket.

## Contract API

| Method | Purpose |
| --- | --- |
| `open_gate(owner, repo, pr_number, base_ref, mandate, allowed_paths_json, consumer)` | Called by the human authorizer. Returns a gate ID. |
| `review_pr(gate_id, expected_head)` | Called by the authorizer or consumer. Returns the verdict and replaces any previous unspent ticket. |
| `get_gate(gate_id)` / `get_report(gate_id)` | Read pinned terms, verdict, file grades, evidence hash, and ticket state. |
| `can_consume(gate_id, head_sha, nonce)` | Check the ticket before consuming it. |
| `consume_ticket(gate_id, head_sha, nonce)` | Only the pinned consumer can spend the ticket. Closes the gate. |
| `close_gate(gate_id)` | Authorizer revokes the gate and any outstanding ticket. |

`allowed_paths_json` is a JSON array. `"src/widget.py"` allows one file; `"src/"` allows files under that directory. `"src"` does not allow the directory. No wildcard or parent traversal is accepted.

Example mandate and path policy:

```text
mandate = "Add a widget parser in src/widget.py and tests in tests/test_widget.py."
allowed_paths_json = '["src/widget.py","tests/test_widget.py"]'
```

The consumer calls `review_pr` with the PR's exact head SHA, reads `get_gate` for the nonce and base SHA, and spends the ticket with that head and nonce. The provided `consumer/merge_consumer.py` checks the current PR head **and base** before and after the spend, then passes the reviewed head in GitHub's merge API `sha` parameter. GitHub documents that this parameter rejects a changed head. The ticket cannot make a chain transaction and GitHub request atomic. A failed GitHub merge leaves the ticket spent and requires a new gate.

## Local development

Requires Python 3.12+, Git, and internet access for the pinned development dependencies:

```bash
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install ".[dev]"
genvm-lint check contracts/mandate_gate.py
python -m pytest -q
```

Direct tests use mocked GitHub and model responses, including a validator disagreement. The RPC integration test runs on GenLayer's GLSim with five simulated validators and mocked GitHub/model responses. To run it locally without Docker:

```bash
python -m pip install ".[dev,sim]"
python -m scripts.run_glsim --port 4000 --validators 5 --no-browser
# In another shell, from this repository:
MANDATEGATE_RUN_INTEGRATION=1 MANDATEGATE_RUN_SIM=1 gltest tests/integration/ -v
```

On PowerShell, set the variables with `$env:MANDATEGATE_RUN_INTEGRATION='1'` and `$env:MANDATEGATE_RUN_SIM='1'` before running `gltest`. `scripts.run_glsim` also handles a Windows temp-file issue in the current direct runner.

GLSim runs the Python runner natively. A full GenVM/Studio consensus check remains necessary before a production deployment. Load `contracts/mandate_gate.py` into GenLayer Studio or use the CLI's direct contract deployment command after selecting and verifying your network:

```bash
genlayer deploy --contract contracts/mandate_gate.py
```

The contract header pins the GenVM runner. The Python development dependencies are pinned to Git commits in `pyproject.toml`.

## Merge consumer

Use a GitHub App or fine-grained token with repository contents write permission and a GenLayer wallet whose address was pinned as `consumer` when the gate opened. Set `GENLAYER_PRIVATE_KEY` and `GITHUB_TOKEN` in your environment; see `.env.example`. The command is a dry run unless `--execute` is supplied:

```bash
python -m consumer.merge_consumer \
  --network studionet --contract 0xDEPLOYED_CONTRACT \
  --gate-id 1 --repo OWNER/REPO --pr 42

python -m consumer.merge_consumer \
  --network studionet --contract 0xDEPLOYED_CONTRACT \
  --gate-id 1 --repo OWNER/REPO --pr 42 --execute
```

The consumer reads finalized gate state, verifies its wallet address and the expected repository/PR, checks the current PR head and base, spends the ticket, waits for finalization, rechecks GitHub, and requests a SHA-pinned squash merge. `--fee-profile path/to/profile.json` accepts measured `consume_ticket` fee allocations if the included baseline is insufficient on your network. Repository branch protection and CI checks remain GitHub's responsibility.

## Boundaries

- Public, same-repository, single-commit PRs only. Private GitHub API access, fork PRs, multi-commit PRs, and PRs whose base moved are `UNVERIFIED` in this version.
- A patch can show *what changed* but cannot prove a program's runtime behavior. `AUTHORIZED` means the diff is judged within the mandate, not that the code is correct or safe.
- GitHub remains the evidence provider and merge authority. The consumer must enforce the reviewed head and base and respect repository branch protection and CI checks.
- The PR is fetched before and after the commit. This detects ordinary changes during review but is not an atomic snapshot of GitHub. A consumer's final head and base check closes that gap at merge time.
- The simulator integration test uses mocked external evidence. A live Studio/testnet review with funded validators has not yet been run.

## References

- [GenLayer equivalence principle](https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle)
- [GenLayer web access](https://docs.genlayer.com/developers/intelligent-contracts/features/web-access)
- [GitHub get a commit API](https://docs.github.com/en/rest/commits/commits)
- [GitHub merge a pull request API](https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request)
