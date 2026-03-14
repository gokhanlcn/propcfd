# gkhncfd

**gkhncfd** is an engineering application for evaluating propeller hydrodynamics and section-based cavitation risk. The application parses HydroComp PropCad (`.hcpc`) datasets to instantiate a blade-element solution enhanced by an analytical ducted-propeller surrogate model for 19A and 37 marine nozzles.

*Developed by AIMLAB*

## Features
- Parses `.hcpc` geometry details dynamically (chord, thickness, pitch, camber)
- Solves open water metrics (KT, KQ, Thrust, Torque, Efficiency)
- Includes engineering surrogate evaluations for continuous-curve Nozzle Performance scaling
- Diagnoses cavitation index mapping at precise blade segments
- Interactive Geometry Viewer integrated natively

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
