import httpx
import orjson

def translate_texts(texts: list[str], to_lang: str, key: str, endpoint: str, region: str, glossary_terms: list[str]) -> list[str]:
    url = f"{endpoint}/translate?api-version=3.0&to={to_lang}"
    headers = {"Ocp-Apim-Subscription-Key": key, "Ocp-Apim-Subscription-Region": region, "Content-Type": "application/json"}
    body = [{"text": text} for text in texts]
    response = httpx.post(url, headers=headers, content=orjson.dumps(body), timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"Translator returned {response.status_code}: {response.text}")
    parsed = response.json()
    if not isinstance(parsed, list):
        raise RuntimeError(f"Unexpected translator payload: {parsed}")
    output = [item["translations"][0]["text"] for item in parsed if "translations" in item]
    if glossary_terms:
        output = [apply_do_not_translate(text, glossary_terms) for text in output]
    return output

def apply_do_not_translate(text: str, terms: list[str]) -> str:
    for term in terms:
        text = text.replace(term, term)
    return text
