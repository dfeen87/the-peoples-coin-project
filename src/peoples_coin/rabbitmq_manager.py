import pika
import time
import logging

logger = logging.getLogger(__name__)

class RabbitMQConnectionManager:
    def __init__(self, amqp_url, max_retries=5, retry_delay=5):
        """
        amqp_url: The RabbitMQ connection string (e.g. amqp://user:pass@host:port/vhost)
        max_retries: Number of retry attempts before fallback
        retry_delay: Seconds to wait between retries
        """
        self.amqp_url = amqp_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connection = None
        self.channel = None

    def connect(self):
        retries = 0
        while retries < self.max_retries:
            try:
                parameters = pika.URLParameters(self.amqp_url)
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                logger.info("🐇 RabbitMQ connected successfully.")
                return True
            except Exception as e:
                logger.warning(f"RabbitMQ connection failed (attempt {retries+1}/{self.max_retries}): {e}")
                retries += 1
                time.sleep(self.retry_delay)
        logger.error("RabbitMQ connection failed after max retries. Falling back.")
        self.connection = None
        self.channel = None
        return False

    def is_connected(self):
        return self.connection is not None and self.connection.is_open

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("🐇 RabbitMQ connection closed.")

    # Add any additional methods you use for publishing/consuming here,
    # but always check is_connected() before using self.channel

