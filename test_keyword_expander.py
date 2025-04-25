from NeedleRef.keyword_expander import expand

# Test various queries
test_queries = [
    "dragon",
    "skull tattoo",
    "hand drawing",
    "mountain landscape",
    "rose flower",
    "japanese-irezumi koi fish"  # already has a style
]

# Run tests
for query in test_queries:
    print(f"\nOriginal query: '{query}'")
    expanded = expand(query)
    print(f"Expanded to {len(expanded)} queries:")
    for idx, exp_query in enumerate(expanded, 1):
        print(f"  {idx}. {exp_query}")