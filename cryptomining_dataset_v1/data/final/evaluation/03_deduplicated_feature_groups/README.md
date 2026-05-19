# Deduplicated Near-Identical Feature Groups

Rows are grouped by scalar model-input feature vectors after applying schema
padding and rounding float values to 6 significant digits. The generated split
keeps each near-identical group entirely in one split so final evaluation does
not leak duplicate-like feature vectors across train and test.
