"""Abhedit content engine: source-locked research, validation and approval gate.

This package never publishes anything. It produces a reviewable content package
(output/packages/<date>/package.json) that a human approves before any publisher
(for example the existing n8n workflow) is allowed to use it.
"""

__version__ = "0.1.0"
