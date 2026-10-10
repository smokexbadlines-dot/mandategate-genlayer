"""The bridge must fail closed before touching the GitHub merge endpoint."""

import pytest

from consumer.merge_consumer import MergePlan, execute_merge, prepare_merge


HEAD = "a" * 40
BASE = "b" * 40
CONSUMER = "0x" + "1" * 40


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class Session:
    def __init__(self, pr):
        self.pr = pr
        self.get_count = 0
        self.put_count = 0

    def get(self, url, timeout):
        self.get_count += 1
        return Response(self.pr)

    def put(self, url, json, timeout):
        self.put_count += 1
        assert json["sha"] == HEAD
        return Response({"merged": True})


class Client:
    def __init__(self):
        self.gate = {
            "consumer": CONSUMER, "repo": "octocat/widgets", "pr_number": 7,
            "is_open": True, "ticket_open": True, "ticket_used": False,
            "verdict": "AUTHORIZED", "reviewed_head": HEAD, "reviewed_base": BASE,
            "base_ref": "main", "nonce": 1,
        }
        self.spends = 0
        self.execution_result = "FINISHED_WITH_RETURN"

    def read_contract(self, address, function_name, args, transaction_hash_variant):
        if function_name == "get_gate":
            return self.gate
        if function_name == "can_consume":
            return self.gate["ticket_open"] and not self.gate["ticket_used"]
        raise AssertionError(function_name)

    def estimate_transaction_fees(self, options):
        return {"distribution": {}, "feeValue": 1}

    def write_contract(self, **kwargs):
        self.spends += 1
        self.gate.update(is_open=False, ticket_open=False, ticket_used=True)
        return "0xticket"

    def wait_for_transaction_receipt(self, **kwargs):
        return {"tx_execution_result_name": self.execution_result, "status_name": "FINALIZED"}


def pr_data():
    return {
        "number": 7, "state": "open", "draft": False, "merged": False,
        "head": {"sha": HEAD, "repo": {"full_name": "octocat/widgets"}},
        "base": {"sha": BASE, "ref": "main", "repo": {"full_name": "octocat/widgets"}},
    }


def prepare(client=None, session=None):
    client = client or Client()
    session = session or Session(pr_data())
    plan = prepare_merge(client, session, "0xcontract", "1", "octocat/widgets", 7, CONSUMER)
    return client, session, plan


def test_consumer_spends_then_merges_exact_head():
    client, session, plan = prepare()
    assert execute_merge(client, object(), session, "0xcontract", plan) == "0xticket"
    assert client.spends == 1
    assert session.get_count == 2
    assert session.put_count == 1


def test_changed_base_prevents_spend():
    client = Client()
    pr = pr_data()
    pr["base"]["sha"] = "c" * 40
    session = Session(pr)
    with pytest.raises(RuntimeError, match="PR head, base"):
        prepare(client, session)
    assert client.spends == 0
    assert session.put_count == 0


def test_wrong_consumer_prevents_spend():
    client = Client()
    client.gate["consumer"] = "0x" + "2" * 40
    session = Session(pr_data())
    with pytest.raises(RuntimeError, match="named consumer"):
        prepare(client, session)
    assert session.get_count == 0


def test_failed_ticket_transaction_never_calls_merge():
    client, session, plan = prepare()
    client.execution_result = "FINISHED_WITH_ERROR"
    with pytest.raises(RuntimeError, match="Ticket spend failed"):
        execute_merge(client, object(), session, "0xcontract", plan)
    assert session.put_count == 0


def test_pr_change_after_spend_never_calls_merge():
    client, session, plan = prepare()
    session.pr["head"]["sha"] = "c" * 40
    with pytest.raises(RuntimeError, match="PR head, base"):
        execute_merge(client, object(), session, "0xcontract", plan)
    assert session.put_count == 0
