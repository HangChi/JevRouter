"""Offline evaluation package for the JevRouter routing decision.

The eval library depends only on ``jev_router`` public interfaces: a fixed case
set is replayed through the same Router, PolicyEngine and tools the agent uses,
plus an LLM baseline router for comparison. ``evals.cli`` is the only module
allowed to cross into ``apps/`` (to post a report), and it does so over HTTP.
"""
