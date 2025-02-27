import os

from pathlib import Path

# TODO Better to use paths without spaces

# Source paths
DECLENSIONS_AND_CONJUGATIONS_FILE = Path("declensions & conjugations.xlsx")
DECLENSIONS_AND_CONJUGATIONS_OVERRIDES_FILE = Path("declensions_n_conjugations_overrides.xlsx")
DPS_DIR = Path(os.getenv("DPS_DIR", "../"))
CSCD_DIR = Path(os.getenv(
    "CSCD_DIR",
    "/home/deva/Documents/dpd-br/pure-machine-readable-corpus/cscd/"))  # TODO Path should not be absolute

# Output paths
OUTPUT_DIR = Path("output")
ALL_INFLECTIONS_FILE = OUTPUT_DIR/"all inflections.csv"
NEW_INFLECTIONS_FILE = OUTPUT_DIR/"new inflections.csv"
ALL_INFLECTIONS_TRANSLIT_FILE = OUTPUT_DIR/"all inflections translit.csv"
NEW_INFLECTIONS_TRANSLIT_FILE = OUTPUT_DIR/"new inflections translit.csv"
INFLECTIONS_DIR = OUTPUT_DIR/"inflections"
INFLECTIONS_TRANSLIT_DIR = OUTPUT_DIR / "inflections translit"
HTML_TABLES_DPS_DIR = OUTPUT_DIR/"html_tables_dps"
HTML_TABLES_SBS_DIR = OUTPUT_DIR/"html_tables_sbs"
HTML_SUTTAS_DIR = OUTPUT_DIR/"html suttas"
