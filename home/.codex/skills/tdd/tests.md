# Good and Bad Tests

## Good Tests

**Integration-style**: Test through real interfaces, not mocks of internal parts.

```typescript
// GOOD: Tests observable behavior
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

Characteristics:

- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

## Bad Tests

**Implementation-detail tests**: Coupled to internal structure.

```typescript
// BAD: Tests implementation details
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

Red flags:

- Mocking internal collaborators
- Testing private methods
- Asserting on call counts/order
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of interface

```typescript
// BAD: Bypasses interface to verify
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: Verifies through interface
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

**Tautological tests**: Expected value restates the implementation, so the test passes by construction.

```typescript
// BAD: Expected value is recomputed the way the code computes it
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// GOOD: Expected value is an independent, known literal
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```

**Setup-heavy tests**: the prologue that reaches the behaviour dwarfs the claim about it.

```python
# BAD: six construction steps, then the claim — repeated verbatim in every test in the file
def test_late_terminal_does_not_pollute_next_start() -> None:
    source = FakeSource()
    module = ApplicationModule(source=source, lifecycle=FakeLifecycle(), owner=ManualScheduler())
    module.start()
    epoch = uuid4()
    hello = module.gateway.negotiate(client_hello(epoch))
    stream = module.gateway.watch(StreamRequest(hello.instance_id, epoch))
    bootstrap = module.gateway.bootstrap(
        AttachRequest(hello.instance_id, epoch, stream.hello.stream_id)
    )
    first = module.gateway.dispatch(
        CommandEnvelope(hello.instance_id, epoch, 1, StartRun("tab-a"),
                        expected_revision=bootstrap.revision)
    )
    assert isinstance(first, CommandSuccess)
    assert isinstance(first.value, OperationStarted)
    ...

# GOOD: the prologue is a fixture, narrowing is a helper, the body is only the claim
def test_late_terminal_does_not_pollute_next_start(attached: AttachedModule) -> None:
    first = expect_started(attached.start_run("tab-a"))
    attached.finish_run("tab-a", operation_id=first.operation_id)
    second = expect_started(attached.start_run("tab-a"))

    attached.finish_run("tab-a", operation_id=first.operation_id)  # the late terminal

    assert attached.next_frame(timeout=0.05) is None
    assert expect_settled(attached.finish_run("tab-a", operation_id=second.operation_id))
```

The fixture and the helpers are written once. Note what the rewrite exposes: the original was hard
to read not because the behaviour is subtle, but because six construction steps stood between the
reader and the claim.

**Type-narrowing as assertion**: assertions written for the type checker, not for the reader.

```python
# BAD: three of the four assertions verify nothing a reader cares about
result = gateway.dispatch(envelope)
assert isinstance(result, CommandSuccess)
assert isinstance(result.value, OperationStarted)
assert result.value.token is not None and isinstance(result.value.token, OperationToken)
assert result.value.token.operation_id == "41"

# GOOD: one narrowing helper, one claim
def expect_started(result: CommandOutcome) -> OperationStarted:
    assert isinstance(result, CommandSuccess), f"expected success, got {result!r}"
    assert isinstance(result.value, OperationStarted), f"expected start, got {result.value!r}"
    return result.value

assert expect_started(gateway.dispatch(envelope)).token.operation_id == "41"
```

`assert x is not None and isinstance(x, T)` is redundant in both halves — `isinstance` already
excludes `None`. At scale this pattern is a reliable sign the suite is being written to satisfy a
type checker rather than to describe behaviour.
