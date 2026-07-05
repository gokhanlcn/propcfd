"""Command-line validation entry point.

Runs the open-water BEMT-vs-Wageningen-B-polynomial report and the ducted-mode
physical-sanity report over the bundled example geometries.

Usage (from the prop_app directory):
    venv\\Scripts\\python tools\\validate.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)            # prop_app/
REPO = os.path.dirname(PROJECT)            # repo root holding B_hcpc / KA_HCPC
sys.path.insert(0, PROJECT)

from src.hydro.validation import run_b_series_report, print_detail, run_ducted_sanity  # noqa: E402

if __name__ == "__main__":
    b_glob = os.path.join(REPO, "B_hcpc", "B*.hcpc")
    ka_glob = os.path.join(REPO, "KA_HCPC", "KA*.hcpc")
    run_b_series_report(b_glob)
    import glob
    files = sorted(glob.glob(b_glob))
    if files:
        print_detail(files[0])
    run_ducted_sanity(ka_glob)
