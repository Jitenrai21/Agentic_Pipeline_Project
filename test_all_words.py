"""Print all words in page."""
import json

data = json.load(open('cache/source_1/pages/page_2.json'))
words = data.get('words', [])

print(f'Total words: {len(words)}')
print('\nFirst 50 words:')
for i, w in enumerate(words[:50]):
    print(f'{i}: x=[{w["x0"]:.1f}-{w["x1"]:.1f}] y=[{w["y0"]:.1f}-{w["y1"]:.1f}] text="{w["text"]}"')
