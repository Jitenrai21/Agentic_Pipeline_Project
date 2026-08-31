"""Find labels in Source 1."""
import json

data = json.load(open('cache/source_1/pages/page_2.json'))
words = data.get('words', [])

# Find all unique words at x < 200 (likely labels)
label_words = set()
for w in words:
    if w['x0'] < 200:
        label_words.add(w['text'])

print('Words at x < 200 (potential labels):')
for word in sorted(label_words):
    print(f'  {word}')
