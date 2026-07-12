import time
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

client = OpenAI(base_url="http://192.168.0.100:1234/v1", api_key="lm-studio")

MODEL = "google/gemma-4-26b-a4b-it"
PROMPT = "Write a detailed 500-word essay about the history of computers."
CONCURRENCY = 10


def benchmark(req_idx: int) -> dict | None:
    try:
        return _benchmark(req_idx)
    except Exception as e:
        print(f"[Request {req_idx:2d}] FAILED: {e}")
        return None


def _benchmark(req_idx: int) -> dict:
    start = time.perf_counter()
    first_token_time = None
    text_parts = []
    usage = None

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=1024,
        temperature=0.7,
        stream=True,
        stream_options={"include_usage": True},  # LM Studio returns token usage in the final chunk
    )

    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            text_parts.append(chunk.choices[0].delta.content)

    end = time.perf_counter()

    total_time = end - start
    ttft = (first_token_time - start) if first_token_time else 0.0

    if usage:
        completion_tokens = usage.completion_tokens
        prompt_tokens = usage.prompt_tokens
    else:
        # fallback: rough estimate if server doesn't report usage
        completion_tokens = int(len("".join(text_parts)) / 4)
        prompt_tokens = -1

    tps = completion_tokens / total_time if total_time > 0 else 0.0

    print(
        f"[Request {req_idx:2d}] prompt={prompt_tokens} completion={completion_tokens} "
        f"ttft={ttft:.2f}s total={total_time:.2f}s tps={tps:.2f}"
    )

    return {"tokens": completion_tokens, "total_time": total_time, "tps": tps, "ttft": ttft}


if __name__ == "__main__":
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        results = [r for r in pool.map(benchmark, range(1, CONCURRENCY + 1)) if r]
    wall_time = time.perf_counter() - wall_start

    if not results:
        raise SystemExit("All requests failed.")

    total_tokens = sum(r["tokens"] for r in results)
    avg_ttft = sum(r["ttft"] for r in results) / len(results)
    avg_req_tps = sum(r["tps"] for r in results) / len(results)

    print()
    print("=== Summary ===")
    print(f"Concurrent requests:    {CONCURRENCY} ({len(results)} succeeded)")
    print(f"Total tokens:           {total_tokens}")
    print(f"Wall time:              {wall_time:.2f} s")
    print(f"Avg time to 1st token:  {avg_ttft:.2f} s")
    print(f"Avg per-request tok/s:  {avg_req_tps:.2f}")
    print(f"Aggregate tok/s:        {total_tokens / wall_time:.2f}")
