"""Find specific words in cache."""
import json

data = json.load(open('cache/source_1/pages/page_2.json'))
words = data.get('words', [])

# Find words containing specific text
search_terms = ['Max', 'PV', 'Power', 'power', 'Weight', 'weight']

for w in words:
    for term in search_terms:
        if term in w['text']:
            print(f'x=[{w["x0"]:.1f}-{w["x1"]:.1f}] y=[{w["y0"]:.1f}-{w["y1"]:.1f}] text="{w["text"]}"')
            break
