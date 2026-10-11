# Run every test: Python behavior tests and repository checks under pytest, then node:test files.
test:
    uv run pytest
    PI_OFFLINE=1 node --test tests/*.test.mjs
