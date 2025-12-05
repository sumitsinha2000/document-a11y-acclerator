# Backend Testing

To run all tests including the slow PDF tests:

```bash
pytest -v
```

To run only fast tests (skip full-PDF tests):

```bash
pytest -v -m "not slow_pdf"
```

To run only the slow PDF tests:

```bash
pytest -v -m slow_pdf
```
