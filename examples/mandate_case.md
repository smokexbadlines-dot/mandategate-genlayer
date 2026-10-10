# Example mandate for a documentation PR

An authorizer can open a gate for a single-commit pull request that adds this file.
The mandate should name `examples/mandate_case.md` and describe the requested text.
The allowed paths JSON should be `["examples/mandate_case.md"]`.

Before review, check that the pull request is open, has one commit, and its base
branch still points to that commit's sole parent. Call `review_pr` with the full
lowercase head SHA. An `AUTHORIZED` report opens a ticket for the named consumer.

The consumer must read finalized gate state, check the pull request's head and
base again, spend the ticket, and submit a GitHub merge with the reviewed head
SHA. If the head or base moves, abandon that ticket and request a new review.
