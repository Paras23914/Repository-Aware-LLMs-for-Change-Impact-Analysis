import json, sys, time, urllib.request, pathlib

URL = "http://127.0.0.1:11434/api/generate"
NUM_CTX = 32768

def measure(path):
    prompt = pathlib.Path(path).read_text(encoding="utf-8")
    body = {
        "model": "qwen2.5-coder:7b",
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": NUM_CTX, "num_predict": 1, "temperature": 0.0, "seed": 42},
    }
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.load(resp)
    return len(prompt), data.get("prompt_eval_count"), round(time.time() - start, 1)

for p in sys.argv[1:]:
    chars, tokens, secs = measure(p)
    flag = "  <-- likely TRUNCATED (at the window limit)" if tokens and tokens >= NUM_CTX - 64 else ""
    print(f"{pathlib.Path(p).name}: {chars} chars, {tokens} prompt tokens, {secs}s{flag}")
