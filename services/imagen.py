# services/imagen.py
"""
Unified helper for Google Imagen 3 (via google‑generativeai 0.8+).

Usage:
    client = ImagenClient(API_KEY)
    bytes_blob = client.generate_image_bytes("a red rose")[0]
"""

from __future__ import annotations

import base64
import json
import logging
import os
from io import BytesIO
from typing import List

import requests
from PIL import Image

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None  # handled later

log = logging.getLogger(__name__)


class ImagenClient:
    def __init__(self, api_key: str, model: str = "imagen-3.0-generate-002") -> None:
        self._api_key = api_key
        self._model_name = model

        self._use_sdk = genai is not None
        if self._use_sdk:
            genai.configure(api_key=api_key)
            self._model_obj = genai.GenerativeModel(model)
            log.info("ImagenClient initialised with google‑generativeai SDK")
        else:
            log.info("ImagenClient will fall back to REST calls (SDK missing)")

    # ------------------------------------------------------------------ SDK ---
    def _sdk_generate(self, prompt: str, n: int, aspect: str) -> List[bytes]:
        """Generate via google‑generativeai (SDK ≥ 0.8.x)."""
        # Some intermediate 0.8 builds use generate_image(); others generate_images()
        if hasattr(self._model_obj, "generate_images"):
            resp = self._model_obj.generate_images(
                prompt=prompt,
                number_of_images=n,
                aspect_ratio=aspect,
            )
            images = resp.generated_images
            return [img.image.image_bytes for img in images]

        if hasattr(self._model_obj, "generate_image"):
            img = self._model_obj.generate_image(
                prompt=prompt,
                aspect_ratio=aspect,
            )
            return [img.image.image_bytes]

        raise RuntimeError("Installed google‑generativeai SDK lacks image methods")

    # --------------------------------------------------------------- REST -----
    def _rest_generate(self, prompt: str, n: int, aspect: str) -> List[bytes]:
        """Generate via public REST predict endpoint (no SDK)."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model_name}:predict?key={self._api_key}"
        )
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": n, "aspectRatio": aspect},
        }
        r = requests.post(url, json=payload, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"REST predict failed: {r.status_code} – {r.text[:200]}")
        data = r.json()
        return [
            base64.b64decode(inst["bytesBase64Encoded"])
            for inst in data["predictions"]
        ]

    # ------------------------------------------------------- Public method ----
    def generate_image_bytes(
        self, prompt: str, *, n: int = 1, aspect: str = "16:9"
    ) -> List[bytes]:
        """Return a list of raw image byte blobs."""
        log.debug("Imagen prompt: %s", prompt[:120])
        if self._use_sdk:
            try:
                return self._sdk_generate(prompt, n, aspect)
            except Exception as e:  # pragma: no cover
                log.warning("SDK path failed (%s), falling back to REST", e)

        return self._rest_generate(prompt, n, aspect)