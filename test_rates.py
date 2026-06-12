import json
import re

# Parse all sample data files through the extractor
from app.services.scrutiny_extract import _get_client, run_scrutiny_pipeline
from app.services.scrutiny_classify import classify_by_filename
import glob

files = glob.glob("SampleData/*/*.pdf")
for f in files:
    print(f"File: {f}")
