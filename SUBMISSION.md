# MandateGate submission

**Category:** Builder → Intelligent Contracts

**Title:** MandateGate — consensus-reviewed PR mandate enforcement

**Notes / description (under 1,000 characters):**

> MandateGate is a standalone GenLayer intelligent contract for checking whether a proposed GitHub pull request stays within a human-authorized task. The authorizer pins a repository, PR, base branch, mandate, allowed paths, and merge consumer. The contract verifies a single-commit PR against GitHub's SHA-pinned commit evidence, then uses GenLayer's LLM and independent validator reviews to grade every changed file. Deterministic rules reject unapproved paths and require explicit mandate text for sensitive files. Only an AUTHORIZED verdict opens a nonce-bound, single-use ticket. A separate consumer spends that ticket after checking the finalized gate and PR head/base, then requests a GitHub merge pinned to the reviewed head SHA. The repository includes a direct test suite, a five-validator GLSim lifecycle test, a fail-closed merge consumer, and documentation of trust limits.

## Evidence to attach

| Type | Evidence | Status |
| --- | --- | --- |
| GitHub Repository | Published repository URL | Pending publication |
| GitHub File | `contracts/mandate_gate.py` URL at the published commit | Pending publication |
| GenLayer Studio Contract | Deployed contract URL and transaction | Pending live Studio deployment |

## Verified locally

- `genvm-lint check contracts/mandate_gate.py`: passed, three checks.
- `python -m pytest -q`: 15 passed, two RPC tests skipped by default.
- `gltest tests/integration/ -q` against GLSim with five validators and mocked external evidence: two passed. The lifecycle includes gate creation, consensus review, ticket spending through the SDK, and a SHA-pinned fake GitHub merge.

GLSim executes Python natively. The Studio deployment and real GenVM validator run must be added as evidence after they succeed. The Portal submission should use the published repository and verified Studio URL, not this local file path.
