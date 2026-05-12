from fastapi import HTTPException

try:
    from ..simfea_api.logger import create_logger
except ImportError:
    from simfea_api.logger import create_logger

log = create_logger("inference")


def completions(data):
    try:
        prompt: str = data["prompt"]
        log.info(f"Sent prompt: '{prompt}'")
        return {"message": f"query: [{prompt}]\nanswer: [...]"}
    except KeyError:
        log.error("Expected format {'prompt':'text string here'}")
        raise HTTPException(
            status_code=400, detail="Invalid JSON format: 'prompt' key not found"
        )
