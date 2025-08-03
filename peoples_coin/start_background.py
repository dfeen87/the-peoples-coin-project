import logging
from peoples_coin import endocrine_system, cognitive_system

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("Starting Endocrine System background process...")
    endocrine_system.start()

    logger.info("Starting Cognitive System background loop...")
    cognitive_system.start_background_loop()

    logger.info("Background processes are running. Press Ctrl+C to exit.")

    # Keep the script running so background loops stay alive
    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Background processes stopped by user.")

