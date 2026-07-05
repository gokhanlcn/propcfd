# gkhncfd

**gkhncfd** is an engineering application for evaluating propeller hydrodynamics and section-based cavitation risk. The application parses HydroComp PropCad (`.hcpc`) datasets to instantiate a blade-element solution enhanced by an analytical ducted-propeller surrogate model for 19A and 37 marine nozzles.

*Developed by AIMLAB*

## Features
- Parses `.hcpc` geometry details dynamically (chord, thickness, pitch, camber)
- Solves open-water metrics (KT, KQ, thrust, torque, efficiency) with a
  Glauert blade-element momentum method (axial + swirl induction)
- Open-water level is calibrated/validated against the **Wageningen B-series
  polynomial** (Oosterveld & van Oossanen 1975) for recognised series
- **Ducted (19A / 37) thrust from self-consistent actuator-disk-in-duct
  momentum theory** — no double counting, realistic bollard augmentation and
  efficiency, duct drag at high advance ratio
- **Bounded cavitation model**: sheet (-Cp_min), tip-vortex (McCormick), and an
  independent Burrill back-cavitation cross-check; duct tip-vortex suppression
- Interactive Geometry Viewer integrated natively

## Physics package and validation
The numerics live in `src/hydro/`:

| Module | Role |
| --- | --- |
| `polynomials.py` | Validated Wageningen B-series KT/KQ (literature "truth") |
| `openwater.py` | Glauert BEMT (axial + swirl induction) |
| `ducted.py` | Actuator-disk-in-duct momentum model (19A / 37) |
| `cavitation.py` | Bounded sheet + tip-vortex + Burrill cavitation |
| `reference.py` | Series detection + polynomial calibration of the BEMT level |
| `validation.py` | Model-vs-polynomial error + ducted physical-sanity reports |

Run the validation harness (definition of done):

```bash
venv\Scripts\python tools\validate.py
```

It reports BEMT-vs-B-series RMS error over `B_hcpc/B*.hcpc` and the ducted
physical-sanity table over `KA_HCPC/KA*.hcpc` (bollard augmentation ~1.4x,
efficiency < 1, monotone thrust). For B-series files the headline open-water
KT/KQ are calibrated to match the polynomial exactly; the BEMT supplies the
radial load distribution used by the cavitation model.

> Note: the Ka-series ducted polynomial coefficients are **not** bundled — every
> open-source set we could verify (and the ones previously in the repo) evaluate
> to non-physical curves. The duct is therefore modelled from first principles
> rather than from fabricated coefficients. See `src/hydro/polynomials.py`.

## Requirements & Deployment
The repository is structured to be immediately deployable to environments like **Streamlit Community Cloud** or local virtual servers. 

Ensure the main execution script is directed towards `app.py`. The `requirements.txt` handles all fundamental python numeric and UI libraries.

### Running Locally
```bash
# 1. Prepare environment
python -m venv venv
.\venv\Scripts\activate  # Windows

# 2. Install Dependencies
pip install -r requirements.txt

# 3. Launch App
streamlit run app.py
```

### Deploying to Streamlit Community Cloud
1. Upload/Push this repository to your GitHub account (make sure the `assets/` directory is included).
2. Log into [Streamlit Community Cloud](https://share.streamlit.io/).
3. Connect your GitHub repository and select the branch.
4. Set the **Main file path** to `app.py`.
5. Click **Deploy**. Streamlit Cloud will automatically install dependencies from `requirements.txt` and launch the app.

### AIMLAB Branding Note
The application targets an `assets/` directory explicitly for custom branding integration via Streamlit's official `st.logo()` element. If you wish to inject your custom logo into the sidebar header, simply place an `aimlab_logo.png` image file directly inside the `assets/` directory. If missing, it will safely fallback to a badge.
