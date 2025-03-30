import os

from zexporta.config import (
    CHAINS_CONFIG,
    ENVIRONMENT,
    SENTRY_DNS,
    ZEX_ENCODE_VERSION,
)
from zexporta.custom_types import EnvEnum

LOGGER_PATH = "/var/log/validator/validator.log"

if EnvEnum.PROD == ENVIRONMENT:
    VALIDATED_IPS = {
        "164.90.163.234": [
            "/pyfrost/v1/dkg/round1",
            "/pyfrost/v1/dkg/round2",
            "/pyfrost/v1/dkg/round3",
            "/pyfrost/v1/sign",
            "/pyfrost/v1/generate-nonces",
        ],
        "172.20.0.1": [
            "/pyfrost/v1/dkg/round1",
            "/pyfrost/v1/dkg/round2",
            "/pyfrost/v1/dkg/round3",
            "/pyfrost/v1/sign",
            "/pyfrost/v1/generate-nonces",
        ],
    }
else:
    VALIDATED_IPS = {
        "172.20.0.4": [
            "/pyfrost/v1/dkg/round1",
            "/pyfrost/v1/dkg/round2",
            "/pyfrost/v1/dkg/round3",
            "/pyfrost/v1/sign",
            "/pyfrost/v1/generate-nonces",
        ],
        "172.20.0.5": [
            "/pyfrost/v1/dkg/round1",
            "/pyfrost/v1/dkg/round2",
            "/pyfrost/v1/dkg/round3",
            "/pyfrost/v1/sign",
            "/pyfrost/v1/generate-nonces",
        ],
    }
PRIVATE_KEY = int(os.environ["NODE_PRIVATE_KEY"])

MAX_WORKERS = int(os.environ["MAX_WORKERS"])
