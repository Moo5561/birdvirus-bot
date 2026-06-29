#!/bin/bash
echo "Installing Playwright..."
pip install playwright
playwright install chromium
echo "Done."
