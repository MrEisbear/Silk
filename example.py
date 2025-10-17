meta = {
    "id": "eisbear.example",
    "name": "Eisbears Example",
    "version": "1.0.0",
    "depends": {
        "hard": {},
        "soft": {} 
    }
}

def init(context):
    logger = context["logger"]
    logger.info(f"{meta['name']} loaded successfully!")