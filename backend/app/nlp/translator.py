import httpx
import orjson

def translate_texts(texts: list[str], to_lang: str, key: str, endpoint: str, region: str, glossary_terms: list[str]) -> list[str]:
    
    url = f"{endpoint}/translate?api-version=3.0&to={to_lang}"
    headers = {"Ocp-Apim-Subscription-Key": key, "Ocp-Apim-Subscription-Region": region, "Content-Type": "application/json"}
    terms_sorted = sorted(glossary_terms, key=len, reverse=True) if glossary_terms else []
    placeholder_map = {f"__GLOSSARY_{i}__": term for i, term in enumerate(terms_sorted)}
    
    # Protect glossary terms before translation and restore after.

    protected_texts = []
    for text in texts:
        protected = text
        for placeholder, term in placeholder_map.items():
            protected = protected.replace(term, placeholder)
        protected_texts.append(protected)

    body = [{"text": text} for text in protected_texts]
    response = httpx.post(url, headers=headers, content=orjson.dumps(body), timeout=10)

    if response.status_code != 200:
        raise RuntimeError(f"Translator returned {response.status_code}: {response.text}")
    parsed = response.json()

    if not isinstance(parsed, list):
        raise RuntimeError(f"Unexpected translator payload: {parsed}")
    output = [item["translations"][0]["text"] for item in parsed if "translations" in item]

    if placeholder_map:
        restored = []
        for text in output:
            restored_text = text
            for placeholder, term in placeholder_map.items():
                restored_text = restored_text.replace(placeholder, term)
            restored.append(restored_text)
        output = restored
    return output
