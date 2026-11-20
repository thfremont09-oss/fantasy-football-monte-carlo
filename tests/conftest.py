"""Shared test setup: stay offline."""

from ffmc import winprob

winprob.USE_RATINGS = False      # team ratings download a season of results; tests use the record-based model
