"""Test spatial extraction with pdfplumber words."""
from src.pipeline.spatial_extractor import load_pdfplumber_words, _cluster_blocks_into_rows, _find_label_block, _find_label_block_multi_word

doc_id = 'source_2'
page_num = 2

blocks = load_pdfplumber_words(doc_id, page_num)
print(f'Loaded {len(blocks)} pdfplumber words')

rows = _cluster_blocks_into_rows(blocks, y_threshold=3.0)
print(f'Clustered into {len(rows)} rows')

print('\nFirst 20 rows:')
for i, row in enumerate(rows[:20]):
    print(f'Row {i} (y={row.y_center:.1f}):')
    for block in row.blocks[:8]:
        print(f'  x=[{block.x0:.1f}-{block.x1:.1f}] text="{block.text}"')
    if len(row.blocks) > 8:
        print(f'  ... and {len(row.blocks)-8} more')

# Test label finding
label = "Rated AC Output Active Power"
result = _find_label_block(rows, label)
if result:
    label_block, row = result
    print(f'\nFound label: "{label_block.text}"')
    print(f'Label x: [{label_block.x0:.1f}-{label_block.x1:.1f}]')
    print(f'Row has {len(row.blocks)} blocks')
    print(f'Blocks to the right:')
    for block in row.blocks_by_x:
        if block.x0 >= label_block.x0:
            print(f'  x=[{block.x0:.1f}-{block.x1:.1f}] text="{block.text}"')
else:
    print(f'\nLabel not found: {label}')
    
    # Try multi-word
    result = _find_label_block_multi_word(rows, label)
    if result:
        label_block, row = result
        print(f'Found via multi-word: "{label_block.text}"')
