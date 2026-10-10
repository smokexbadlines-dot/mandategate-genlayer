# MandateGate submission

**Category:** Builder → Intelligent Contracts

**Title:** MandateGate — consensus-reviewed PR mandate enforcement

**Notes / description (under 1,000 characters):**

> MandateGate is a standalone GenLayer intelligent contract for checking whether a proposed GitHub pull request stays within a human-authorized task. The authorizer pins a repository, PR, base branch, mandate, allowed paths, and merge consumer. The contract verifies a single-commit PR against GitHub's SHA-pinned commit evidence, then uses GenLayer's LLM and independent validator reviews to grade every changed file. Deterministic rules reject unapproved paths and require explicit mandate text for sensitive files. Only an AUTHORIZED verdict opens a nonce-bound, single-use ticket. A separate consumer spends that ticket after checking the finalized gate and PR head/base, then requests a GitHub merge pinned to the reviewed head SHA. The repository includes a direct test suite, a five-validator GLSim lifecycle test, a fail-closed merge consumer, and documentation of trust limits.

## Evidence to attach

| Type | Evidence | Status |
| --- | --- | --- |
| GitHub Repository | https://github.com/smokexbadlines-dot/mandategate-genlayer | Published |
| GitHub File | https://github.com/smokexbadlines-dot/mandategate-genlayer/blob/main/contracts/mandate_gate.py | Published |
| GenLayer Studio Contract | https://explorer-studio.genlayer.com/address/0xB298A1818E18e9Af55f9312C1D1e862f31d9e699 | Deployment finalized; constructor succeeded |
| Studio deployment transaction | https://explorer-studio.genlayer.com/tx/0x5754abc49e13db4c40c0c1d3283021346933eceef0bbb92cc555590787e955ac | Finalized |

## Verified locally

- `genvm-lint check contracts/mandate_gate.py`: passed, three checks.
- `python -m pytest -q`: 15 passed, two RPC tests skipped by default.
- `gltest tests/integration/ -q` against GLSim with five validators and mocked external evidence: two passed. The lifecycle includes gate creation, consensus review, ticket spending through the SDK, and a SHA-pinned fake GitHub merge.

GLSim executes Python natively. The Studio deployment passed full consensus and finalized. A live review against an actual GitHub PR is still pending. The Portal submission should use the repository and Studio URLs above.
