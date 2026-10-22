.PHONY: test demo serve profiles clean

test:
	PYTHONPATH=src python -m pytest -q

demo:
	python examples/run_demo.py

serve:
	customer-data-platform serve --port 8000

profiles:
	customer-data-platform profiles

clean:
	rm -rf .pytest_cache
