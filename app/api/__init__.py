"""
HTTP routes only. Each route turns a web request into a function call
elsewhere (agent/, db/) and turns the result back into JSON. No logic here,
so the CLI and (later) scheduled routines can call the same functions.
"""
