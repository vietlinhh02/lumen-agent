"""Sandbox subsystem for the Lumen assistant.

Provides per-project isolated execution environments so the agent can
do more than what the in-process fast-path tools allow: run Python,
manipulate files, inspect PDFs, and (optionally) install packages.

Two run modes are supported:

* **docker** — spin up a real container per project (production).
* **stub** — same interface, but executes locally in a subprocess.
  Used for unit tests and local dev without Docker.
* **disabled** — fast-path tools stay available, sandbox tools return
  an "ENABLE_SANDBOX is off" error.

The router in ``app.services.sandbox.router`` dispatches each tool by
name to either the local tool registry or a remote sandbox HTTP call.
"""
