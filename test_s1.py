"""Test spatial extraction on Source 1."""
from src.pipeline.spatial_extractor import load_pdfplumber_words, _cluster_blocks_into_rows, _find_label_block_multi_word, find_row_value_spatial

doc_id = 'source_1'
page_num = 2

blocks = load_pdfplumber_words(doc_id, page_num)
print(f'Loaded {len(blocks)} pdfplumber words')

rows = _cluster_blocks_into_rows(blocks, y_threshold=3.0)
print(f'Clustered into {len(rows)} rows')

# Test finding labels
labels = [
    "Max. PV Input Power",
    "Rated AC Output Active Power",
    "Max. Efficiency",
    "Weight",
]

col_idx = 1  # SUN-5K column

for label in labels:
    result = find_row_value_spatial(rows, label, col_idx)
    if result:
        value, unit, extract_type = result
        print(f'{label}: value={value}, unit={unit}, type={extract_type}')
    else:
        print(f'{label}: NOT FOUND')
