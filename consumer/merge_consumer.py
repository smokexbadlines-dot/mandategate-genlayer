"""Spend an authorized MandateGate ticket, then merge the pinned GitHub PR.

The GitHub merge is deliberately after a finalized ticket spend. If GitHub rejects
the merge, the ticket stays spent; the authorizer must open a new gate.
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass

import requests
from genlayer_py import create_account, create_client
from genlayer_py.chains import localnet, studionet, testnet_bradbury
from genlayer_py.types.transactions import TransactionHashVariant, TransactionStatus


CHAINS = {"localnet": localnet, "studionet": studionet, "bradbury": testnet_bradbury}
GITHUB_API = "https://api.github.com"
FINAL = TransactionHashVariant.LATEST_FINAL
DEFAULT_FEE_PROFILE = {
    "leaderTimeunitsAllocation": 125,
    "validatorTimeunitsAllocation": 250,
    "rotations": [0],
}


@dataclass(frozen=True)
class MergePlan:
    gate_id: str
    repo: str
    pr_number: int
    head: str
    base: str
    base_ref: str
    nonce: int


def _read_pr(session: requests.Session, plan: MergePlan) -> dict:
    response = session.get(f"{GITHUB_API}/repos/{plan.repo}/pulls/{plan.pr_number}", timeout=20)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("GitHub returned an invalid PR")
    return data


def _assert_pr_unchanged(pr: dict, plan: MergePlan) -> None:
    try:
        okay = (
            pr["number"] == plan.pr_number
            and pr["state"] == "open" and not pr["draft"] and not pr["merged"]
            and pr["head"]["sha"] == plan.head
            and pr["base"]["sha"] == plan.base
            and pr["base"]["ref"] == plan.base_ref
            and pr["base"]["repo"]["full_name"] == plan.repo
            and pr["head"]["repo"]["full_name"] == plan.repo
        )
    except (KeyError, TypeError):
        okay = False
    if not okay:
        raise RuntimeError("PR head, base, or state changed since MandateGate review")


def prepare_merge(client, session: requests.Session, contract: str, gate_id: str,
                  expected_repo: str, expected_pr: int, consumer_address: str) -> MergePlan:
    gate = client.read_contract(address=contract, function_name="get_gate", args=[gate_id],
                                transaction_hash_variant=FINAL)
    if not isinstance(gate, dict):
        raise RuntimeError("Cannot read finalized gate")
    if gate.get("consumer", "").lower() != consumer_address.lower():
        raise RuntimeError("Wallet is not the gate's named consumer")
    if gate.get("repo") != expected_repo or gate.get("pr_number") != expected_pr:
        raise RuntimeError("Gate is for a different repository or PR")
    if (not gate.get("is_open") or not gate.get("ticket_open") or gate.get("ticket_used")
            or gate.get("verdict") != "AUTHORIZED"):
        raise RuntimeError("Gate has no spendable authorized ticket")
    plan = MergePlan(gate_id, expected_repo, expected_pr, gate["reviewed_head"],
                     gate["reviewed_base"], gate["base_ref"], gate["nonce"])
    if not (len(plan.head) == len(plan.base) == 40):
        raise RuntimeError("Gate does not contain full reviewed SHAs")
    spendable = client.read_contract(
        address=contract, function_name="can_consume",
        args=[gate_id, plan.head, plan.nonce], transaction_hash_variant=FINAL,
    )
    if spendable is not True:
        raise RuntimeError("Ticket is unavailable in finalized state")
    _assert_pr_unchanged(_read_pr(session, plan), plan)
    return plan


def execute_merge(client, account, session: requests.Session, contract: str,
                  plan: MergePlan, fee_profile: dict | None = None) -> str:
    args = [plan.gate_id, plan.head, plan.nonce]
    estimate = client.estimate_transaction_fees(fee_profile or DEFAULT_FEE_PROFILE)
    tx_id = client.write_contract(
        account=account, address=contract, function_name="consume_ticket", args=args,
        fees={"distribution": estimate["distribution"], "feeValue": estimate["feeValue"]},
    )
    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx_id, status=TransactionStatus.FINALIZED,
    )
    if (receipt.get("tx_execution_result_name") not in (None, "FINISHED_WITH_RETURN")
            or receipt.get("status_name") != "FINALIZED"):
        raise RuntimeError(
            f"Ticket spend failed; transaction: {tx_id}; "
            f"status={receipt.get('status_name')}, "
            f"result={receipt.get('tx_execution_result_name')}"
        )
    gate = client.read_contract(address=contract, function_name="get_gate", args=[plan.gate_id],
                                transaction_hash_variant=FINAL)
    if not (gate["ticket_used"] and not gate["is_open"]
            and gate["reviewed_head"] == plan.head and gate["nonce"] == plan.nonce):
        raise RuntimeError(f"Finalized ticket state is unexpected; transaction: {tx_id}")
    _assert_pr_unchanged(_read_pr(session, plan), plan)
    response = session.put(
        f"{GITHUB_API}/repos/{plan.repo}/pulls/{plan.pr_number}/merge",
        json={"sha": plan.head, "merge_method": "squash"}, timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or result.get("merged") is not True:
        raise RuntimeError(f"GitHub did not confirm merge; spent ticket: {tx_id}")
    return str(tx_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume a MandateGate ticket and merge its PR")
    parser.add_argument("--contract", required=True, help="Deployed MandateGate address")
    parser.add_argument("--gate-id", required=True)
    parser.add_argument("--repo", required=True, help="Expected owner/repository")
    parser.add_argument("--pr", required=True, type=int, help="Expected PR number")
    parser.add_argument("--network", choices=CHAINS, default="studionet")
    parser.add_argument("--fee-profile", help="JSON fee allocation profile for consume_ticket")
    parser.add_argument("--execute", action="store_true", help="Spend ticket and merge; default is dry run")
    args = parser.parse_args()
    private_key = os.environ.get("GENLAYER_PRIVATE_KEY")
    github_token = os.environ.get("GITHUB_TOKEN")
    if not private_key or not github_token:
        parser.error("GENLAYER_PRIVATE_KEY and GITHUB_TOKEN are required")
    account = create_account(private_key)
    client = create_client(chain=CHAINS[args.network], account=account)
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    plan = prepare_merge(client, session, args.contract, args.gate_id,
                         args.repo, args.pr, account.address)
    if not args.execute:
        print(f"Ready: {plan.repo} PR #{plan.pr_number}, head {plan.head}, base {plan.base}, nonce {plan.nonce}")
        print("Dry run only. Add --execute to spend the ticket and request the merge.")
        return 0
    fee_profile = None
    if args.fee_profile:
        with open(args.fee_profile, encoding="utf-8") as source:
            fee_profile = json.load(source)
        if not isinstance(fee_profile, dict):
            parser.error("Fee profile must be a JSON object")
    tx_id = execute_merge(client, account, session, args.contract, plan, fee_profile)
    print(f"Merged {plan.repo} PR #{plan.pr_number}; spent ticket transaction {tx_id}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, requests.RequestException) as error:
        print(f"Merge stopped: {error}", file=sys.stderr)
        sys.exit(1)
