from fastapi import HTTPException


# Example api logic
def completions(data):
    try:
        prompt: str = data["prompt"]
        print(f"[server] Sent prompt: '{prompt}'", flush=True)
        # Example response
        return {"message": f"query: [{prompt}]\nanswer: [...]"}
    except KeyError:
        print(
            f"[server] Error: Expected format {{'prompt':'text string here'}}",
            flush=True,
        )
        raise HTTPException(
            status_code=400, detail="Invalid JSON format: 'prompt' key not found"
        )
