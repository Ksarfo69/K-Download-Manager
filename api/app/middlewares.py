import logging

from fastapi import Request

logger = logging.getLogger(__name__)


def log_request(req: Request):
    logger.info(f"Request IP: {req.client.host}, Method: {req.method}, URI: {req.url}")
