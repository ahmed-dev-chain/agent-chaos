# Contributing

```bash
pip install -e ".[dev]"
ruff check src tests examples
pytest
```

- Add a fault: subclass `Fault`, implement `apply`, decorate with `@register_fault`, add a unit test.
- Add an oracle: return an `Oracle` from a function in `oracles/`, add tests for pass and fail.
- Keep randomness in `ctx.rng` so seeds replay exactly.
- Public interfaces follow semver once v1.0 ships; propose changes in an issue first.
- Maintainers: see [`RELEASING.md`](RELEASING.md) for how a release gets published to PyPI.
