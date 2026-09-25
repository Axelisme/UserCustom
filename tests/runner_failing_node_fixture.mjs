// Fixture for tests/test_test_runner.py: a node test file that always fails.
import test from "node:test";

test("runner fixture fails", () => {
  throw new Error("NODE-FIXTURE-FAILURE");
});
